import numpy as np
# noinspection PyPackageRequirements
import pandas as pd
import yaml


def main(config, fname=None):
    # Check if input argument is yaml file
    try:
        with open(config, encoding='utf8') as config_file:
            config = yaml.safe_load(config_file)
    except TypeError:
        pass
    except OSError:
        pass

    if isinstance(config, dict):
        frame = single_config(**config)
    else:
        frames = [single_config(**c) for c in config]
        frame = pd.concat(frames)

    if fname is not None:
        frame.to_csv(fname, sep="\t", header=False, index=False,
                     date_format="%Y-%m-%dT%H:%M:%S")

    return frame


def single_config(
    location=None, depth=0, start_time='2000-01-01', stop_time='2000-01-01',
    num_particles=0, group_id=0,
):

    release = pd.DataFrame(
        columns=['active', 'release_time', 'lat', 'lon', 'Z', 'sink_vel', 'group_id'])

    # Handle default arguments
    if location is None:
        location = dict(lat=0., lon=0.)

    # Set parameters
    release['active'] = np.ones(num_particles)
    release['release_time'] = linspace_time(start_time, stop_time, num_particles)
    release['lat'], release['lon'] = latlon(location, num_particles)
    release['Z'] = depth
    release['sink_vel'] = sinkvel(num_particles)
    release['group_id'] = group_id

    return release


def linspace_time(start, stop, num, granularity='ms'):
    start_t = np.datetime64(start)
    stop_t = np.datetime64(stop)
    timediff = (stop_t - start_t) / np.timedelta64(1, granularity)
    dt = np.linspace(0, 1, num) * timediff
    return start_t + dt.astype(f'timedelta64[{granularity}]')


# noinspection PyPackageRequirements
def sinkvel(n):
    from scipy.interpolate import InterpolatedUnivariateSpline
    sinkvel_tab = np.array([.100, .050, .025, .015, .010, .005, 0])
    cumprob_tab = np.array([.000, .662, .851, .883, .909, .937, 1])
    fn = InterpolatedUnivariateSpline(cumprob_tab, sinkvel_tab, k=2)
    return fn(np.random.rand(n))


def latlon(loc, n):
    # If lat/lon is given directly
    if isinstance(loc, dict):
        lat = np.vectorize(to_numeric_latlon)(loc['lat'])
        lon = np.vectorize(to_numeric_latlon)(loc['lon'])

        # If singular point
        if len(lat.shape) == 0 and len(lon.shape) == 0:
            return np.ones(n)*lat, np.ones(n)*lon
        # If polygon
        else:
            return get_polygon_sample_convex(np.array((lat, lon)).T, n)

    else:
        raise NotImplementedError("Database lookup not implemented")


def to_numeric_latlon(lat_or_lon):
    if isinstance(lat_or_lon, str):
        if '°' in lat_or_lon:
            deg_str, rest = lat_or_lon.replace('"', "''").split('°')
            mn = 0
            sec = 0
            if "''" in rest:
                rest = rest.replace("''", "")
                mn_str, sec_str = rest.split("'")
                mn = float(mn_str)
                sec = float(sec_str)
            elif "'" in rest:
                mn = float(rest.replace("'", ""))
            return float(deg_str) + mn/60 + sec/3600
        else:
            return float(lat_or_lon)
    return lat_or_lon


def _unit_triangle_sample(num):
    xy = np.random.rand(num*2).reshape((2, -1))
    is_upper_triangle = np.sum(xy, axis=0) > 1
    xy[:, is_upper_triangle] = 1 - xy[:, is_upper_triangle]
    return xy


def get_polygon_sample(coords, num):
    if is_convex(coords):
        return get_polygon_sample_convex(coords, num)
    else:
        return get_polygon_sample_nonconvex(coords, num)


def triangulate(coords):
    triangles = []
    for i in range(len(coords) - 2):
        idx = [0, i + 1, i + 2]
        triangles.append(coords[idx])
    return np.array(triangles)


def triangulate_nonconvex(coords):
    import triangle as tr

    # Triangulate the polygon
    sequence = list(range(len(coords)))
    trpoly = dict(vertices=coords,
                  segments=np.array((sequence, sequence[1:] + [0])).T)
    trdata = tr.triangulate(trpoly, 'p')
    coords = [trdata['vertices'][tidx] for tidx in trdata['triangles']]
    return np.array(coords)


def triangle_areas(triangles):
    a = triangles[..., 1, :] - triangles[..., 0, :]
    b = triangles[..., 2, :] - triangles[..., 0, :]
    return 0.5 * np.abs(a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0])


def get_polygon_sample_convex(coords, num):
    triangles = triangulate(coords)
    return get_polygon_sample_triangles(triangles, num)


def get_polygon_sample_nonconvex(coords, num):
    triangles = triangulate_nonconvex(coords)
    return get_polygon_sample_triangles(triangles, num)


def get_polygon_sample_triangles(triangles, num):
    np.random.seed(0)

    # Triangulate the polygon
    areas = triangle_areas(triangles)

    # Distribute the points proportionally among the different triangles
    cumarea = np.cumsum(areas)
    triangle_num = np.searchsorted(cumarea / cumarea[-1], np.random.rand(num))

    # Sample within the triangles
    s, t = _unit_triangle_sample(num)
    (x1, x2, x3), (y1, y2, y3) = triangles[triangle_num].T
    x = (x2 - x1) * s + (x3 - x1) * t + x1
    y = (y2 - y1) * s + (y3 - y1) * t + y1
    return x, y


def is_convex(coords):
    # Compute coord differences
    c = np.concatenate([coords, coords[0:2]])
    v = c[:-1, :] - c[1:, :]

    # Compute sign of the cross product
    sgn = v[:-1, 0] * v[1:, 1] > v[:-1, 1] * v[1:, 0]
    # noinspection PyUnresolvedReferences
    return np.all(sgn == sgn[0])


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: make_release <config.yaml> <out.rls>')
    elif len(sys.argv) == 2:
        out = main(sys.argv[1])
        print(out)
    else:
        main(sys.argv[1], sys.argv[2])

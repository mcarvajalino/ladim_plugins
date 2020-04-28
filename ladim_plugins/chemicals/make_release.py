import numpy as np
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


def single_config(location, depth, release_time, num_particles, group_id):

    release = pd.DataFrame(
        columns=['release_time', 'lat', 'lon', 'Z', 'group_id'])

    # Set parameters
    release['lat'], release['lon'] = latlon(location, num_particles)
    release['Z'] = np.linspace(depth[0], depth[1], num_particles)
    release['group_id'] = group_id
    release['release_time'] = release_time

    return release


def latlon(loc, n):
    if isinstance(loc, dict):
        if 'lat' in loc and 'lon' in loc:
            lat = to_numeric_latlon_seq(loc['lat'])
            lon = to_numeric_latlon_seq(loc['lon'])
        elif 'file' in loc:
            raise NotImplementedError()
        else:
            raise NotImplementedError()

        # If square
        if 'width' in loc:
            return latlon_from_llw(lat, lon, loc['width'], n)

        # If singular point
        elif np.shape(lat) == ():
            return np.ones(n) * lat, np.ones(n) * lon

        # If polygon
        else:
            return latlon_from_poly(lat, lon, n)


def latlon_from_llw(lat, lon, width, n):
    (lat1, lat2), (lon1, lon2) = latlon_square(lat, lon, width)
    p = np.array([[lat1, lon1], [lat2, lon1], [lat2, lon2], [lat1, lon2]])
    return get_polygon_sample_convex(p, n)


def latlon_square(lat, lon, width):
    a = 6378137.0
    b = 6356752.314245

    lat_rad = lat * np.pi / 180
    lat_cos = np.cos(lat_rad)
    lat_sin = np.sin(lat_rad)

    lat_width = np.sqrt(width ** 2 / ((a*lat_sin)**2 + (b*lat_cos)**2))
    lon_width = width / (a * lat_cos)

    lat_limits = lat + np.array([-0.5, 0.5]) * lat_width * 180 / np.pi
    lon_limits = lon + np.array([-0.5, 0.5]) * lon_width * 180 / np.pi

    return lat_limits, lon_limits


def latlon_from_poly(lat, lon, n):
    # Make multipolygon if given a single polygon
    if np.shape(lat[0]) == ():
        lat = [lat]
        lon = [lon]

    # For each subpolygon
    triangles = []
    for lat_element, lon_element in zip(lat, lon):
        coords = np.stack((lat_element, lon_element)).T
        triangles += triangulate_nonconvex(coords).tolist()
    return get_polygon_sample_triangles(np.array(triangles), n)


def to_numeric_latlon_seq(lat_or_lon_seq):
    # Find nesting level
    dims = 0
    try:
        if not isinstance(lat_or_lon_seq[0], str):
            dims = 1
        if not isinstance(lat_or_lon_seq[0][0], str):
            dims = 2
    except TypeError:
        pass

    if dims == 0:
        return to_numeric_latlon(lat_or_lon_seq)
    elif dims == 1:
        return np.vectorize(to_numeric_latlon)(lat_or_lon_seq)
    else:  # dims == 2
        fn = np.vectorize(to_numeric_latlon)
        return [fn(val) for val in lat_or_lon_seq]


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


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: make_release <config.yaml> <out.rls>')
    elif len(sys.argv) == 2:
        out = main(sys.argv[1])
        print(out)
    else:
        main(sys.argv[1], sys.argv[2])

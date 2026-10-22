"""Optional bounded tensor masters for existing C1/HVF reconstruction.

The unchanged default remains C1's 27 nodes. This separate 125-node three-axis
profile captures more internal nonlinear variation, while retaining frozen
holdouts, 1/32 errors, failed quantization and all production/native gates.
Finite interpolation improvement is not a continuous error certificate.

Reuses fontTools VariationModel through the existing reconstruction builder.
https://fonttools.readthedocs.io/en/latest/varLib/models.html
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html
"""
from itertools import product


def tensor_training_grid(axis_tags, *, forbidden_locations=()):
    """Return the fixed F2DOT14-exact (-1,-.5,0,.5,1)^N training profile.

    Order the default first, then increasing number of nonzero axes, matching
    C1's existing deterministic ordering convention. Reject a frozen-holdout
    collision rather than silently promoting or removing a validation case.
    No source observations or requested tolerance enter node selection.
    """
    if (type(axis_tags) not in (tuple, list) or not 1 <= len(axis_tags) <= 3
            or any(type(tag) is not str or len(tag) != 4 or not tag.isascii() for tag in axis_tags)
            or len(set(axis_tags)) != len(axis_tags)):
        raise ValueError('one_to_three_unique_axis_tags_required')
    if not all(type(location) is dict and set(location) == set(axis_tags)
               for location in forbidden_locations):
        raise ValueError('all_frozen_holdout_axis_coordinates_required')
    points = list(product((-1., -.5, 0., .5, 1.), repeat=len(axis_tags)))
    points.sort(key=lambda point: (sum(value != 0 for value in point), point))
    forbidden = {tuple(location[tag] for tag in axis_tags) for location in forbidden_locations}
    if any(point in forbidden for point in points):
        raise ValueError('frozen_holdout_collides_with_tensor_training')
    return [dict(zip(axis_tags, point)) for point in points]

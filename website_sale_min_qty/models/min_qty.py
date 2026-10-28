# -*- coding: utf-8 -*-
"""Minimum order quantities and purchase steps.

The arithmetic lives here, away from the ORM, because it is the part that has
to be exactly right: a 0.25 kg step must give 0.75 after three additions, not
0.7500000000000001, and 0.3 must land on 0.5, not on 0.30 with a step printed
next to it. Two separate ideas are involved and they are easy to confuse:

* the *grid* is defined by the step (0.25, 1, 6, ...), and a quantity that is
  not on it is moved **up** to the next grid point;
* the *precision* is the product's UoM rounding. It is only used to remove the
  binary noise that multiplying a grid index by a step can leave behind
  (``3 * 0.1 == 0.30000000000000004``). Rounding to two decimals instead would
  quietly invent a different grid for every product.

A quantity of zero or less is a removal, never an order: it is returned
untouched, so deleting a line is not turned into "buy the minimum".
"""
from odoo.tools import float_compare

#: Relative distance under which a quotient counts as sitting *on* a grid
#: point. Dividing a quantity by its step is a float division: 0.3 / 0.1 is
#: 2.9999999999999996 and 0.7 / 0.1 is 6.999999999999999, both of which would
#: otherwise be pushed a whole step up by ``ceil``. 1e-9 is far above the
#: ~1e-16 relative error of the division and far below any meaningful
#: difference between two quantities.
_GRID_EPSILON = 1e-9

#: How far the search for a value's own number of decimals goes. Nothing a
#: merchant types into a UoM or a step needs more than this.
_MAX_DECIMALS = 12


def _grid_index(value, step):
    """The smallest grid index whose multiple reaches *value*.

    ``value / step`` is a float division, so a value that is on the grid can
    come out a hair below its index. Such a value keeps its index instead of
    climbing one step; anything genuinely between two grid points goes up.
    """
    ratio = value / step
    nearest = round(ratio)
    if abs(ratio - nearest) <= _GRID_EPSILON * max(1.0, abs(ratio)):
        return int(nearest)
    return int(ratio // 1) + 1 if ratio > 0 else int(nearest)


def _decimals(number):
    """The fewest decimals that spell *number* exactly, capped.

    Used to know how far a result is allowed to be cleaned: 0.25 needs two
    decimals, 0.1 needs one, a UoM rounding of 0.001 needs three. Cleaning to
    a fixed number of decimals instead is the mistake this module is about --
    two decimals is not a step.
    """
    number = abs(float(number or 0.0))
    if number == 0:
        return 0
    for digits in range(0, _MAX_DECIMALS + 1):
        if round(number, digits) == number:
            return digits
    return _MAX_DECIMALS


def clean_precision(step, rounding):
    """The number of decimals a snapped quantity is spelled with.

    The UoM rounding is the natural precision, but it can be *coarser* than
    the step: a product sold in Units (rounding 1) that is ordered in quarters
    would have every result rounded to a whole unit, i.e. the step would be
    silently widened. Taking the finer of the two keeps the grid the merchant
    asked for while still removing the noise below it.
    """
    precision = min(step, rounding) if step > 0 else rounding
    return max(_decimals(step), _decimals(precision))


def snap_up(quantity, step, minimum, rounding):
    """Move *quantity* up onto the step grid and up to *minimum*.

    :param float quantity: the quantity the customer asked for
    :param float step: the grid the quantity has to sit on; 0 means no grid
    :param float minimum: the smallest quantity that may be ordered; 0 means
        no minimum
    :param float rounding: the product's UoM rounding, used to decide how the
        result is spelled
    :return: ``(value, changed)`` -- the quantity to use, and whether it
        differs from the one asked for
    :rtype: tuple[float, bool]
    """
    quantity = float(quantity or 0.0)
    step = float(step or 0.0)
    minimum = float(minimum or 0.0)

    # A removal (or an empty request) is never an order: leave it alone, so
    # that a cart line can still be deleted on a product with a minimum.
    if quantity <= 0:
        return quantity, False
    # Neither rule set: the quantity is returned as the very same float, which
    # is what "no side effect" means for a shop that never configured this.
    if step <= 0 and minimum <= 0:
        return quantity, False

    if step > 0:
        target = _grid_index(quantity, step) * step
        if minimum > 0:
            floor = _grid_index(minimum, step) * step
            target = max(target, floor)
    else:
        target = max(quantity, minimum)

    # ``index * step`` is a float product: 3 * 0.1 is 0.30000000000000004 and
    # the customer would read that in the cart. Rounding to the decimals the
    # step and the UoM actually use gives back 0.3, and leaves 0.75 alone.
    target = round(target, clean_precision(step, rounding))

    changed = float_compare(
        quantity, target, precision_rounding=min(step, rounding) if step else rounding) != 0
    return target, changed


def is_on_grid(quantity, step, rounding):
    """Whether *quantity* is already one of the allowed values."""
    if quantity <= 0 or step <= 0:
        return True
    precision = min(step, rounding) if step > 0 else rounding
    return float_compare(quantity, _grid_index(quantity, step) * step,
                         precision_rounding=precision) == 0


def format_quantity(quantity):
    """A quantity as a customer should read it: 5, 0.25, 1.5 -- no `.0`."""
    value = float(quantity or 0.0)
    if value == int(value):
        return str(int(value))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def translate(env, text):
    """Translate *text* with whichever accessor this series provides.

    ``env._`` exists from 18.0 on and is the preferred door; the module-level
    ``_`` is the one 16.0 and 17.0 have. Asking the environment first keeps
    the module importable on a series that has dropped the global function,
    and the global import stays inside the branch that needs it.
    """
    translator = getattr(env, "_", None)
    if callable(translator):
        return translator(text)
    from odoo import _
    return _(text)


def uom_rounding(product):
    """The rounding of *product*'s unit of measure, on every series.

    Odoo 20 removed ``uom.uom.rounding`` and reads the precision from the
    "Product Unit" decimal precision instead. Both are asked for here so the
    same arithmetic serves every version, and a UoM that reports 0 (which
    would make the cleanup a no-op) falls back to the same setting.
    """
    rounding = getattr(product.uom_id, "rounding", 0.0) or 0.0
    if rounding <= 0:
        rounding = 10.0 ** -product.env["decimal.precision"].precision_get("Product Unit")
    return rounding


def snap_for(product, quantity):
    """Round *quantity* up onto *product*'s grid; see :func:`snap_up`."""
    minimum, step = product._min_qty_rules()
    return snap_up(quantity, step, minimum, uom_rounding(product))


def website_of(env):
    """The website a note is read from, request or not.

    ``env.website`` exists from 20.0 on; before that the current website is a
    model method that returns an empty recordset outside a request, in which
    case the first site is a good enough answer for a note.
    """
    website = getattr(env, "website", None)
    if not website:
        getter = getattr(env["website"], "get_current_website", None)
        website = getter() if getter else env["website"].search([], limit=1)
    return website


def web_values(product):
    """The attributes and the sentence the quantity input is rendered with.

    Kept in one dict so the template, the tests and the checkout warning all
    read the same numbers: a ``step`` attribute that disagrees with the
    server-side rounding is a shop that lets the customer type a quantity it
    will then refuse.
    """
    minimum, step = product._min_qty_rules()
    rounding = uom_rounding(product)
    digits = clean_precision(step, rounding)
    default, _changed = snap_up(max(minimum, step or 1.0), step, minimum, rounding)
    website = website_of(product.env)
    return {
        "min_qty_min": round(minimum or 1.0, digits),
        "min_qty_step": round(step or 1.0, digits),
        "min_qty_default": default,
        "min_qty_note": website._min_qty_note(minimum, step) if website else "",
        "min_qty_min_text": format_quantity(minimum),
        "min_qty_step_text": format_quantity(step),
    }

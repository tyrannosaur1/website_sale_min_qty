# -*- coding: utf-8 -*-
"""What a step and a minimum mean, before any cart is involved.

Every assertion here is about a number a customer will read back: the module
fails its purpose if the cart shows 0.30000000000000004 next to a "sold in
multiples of 0.25" sentence, or if a shop that never configured a step gets a
quantity moved by a module it does not use.
"""
from odoo.tests.common import TransactionCase

from odoo.addons.website_sale_min_qty.models.min_qty import (
    format_quantity,
    is_on_grid,
    snap_up,
)


class TestQuantityArithmetic(TransactionCase):
    """The pure functions: no product, no website, only numbers."""

    def test_three_quarter_steps_add_up_exactly(self):
        """0.25 + 0.25 + 0.25 is 0.75, to the last bit."""
        quantity = 0.0
        for _step in range(3):
            quantity, changed = snap_up(quantity + 0.25, 0.25, 0, 0.001)
            self.assertFalse(changed)
        self.assertEqual(quantity, 0.75)
        self.assertEqual(repr(quantity), "0.75")
        self.assertEqual(quantity * 4, 3.0)

    def test_a_tenth_of_a_unit_leaves_no_binary_noise(self):
        """3 * 0.1 must come back as 0.3, not 0.30000000000000004.

        The grid is right (0.3 is a multiple of 0.1); what is wrong is how the
        product is spelled. This is the case a "round to two decimals" fix
        would hide and a "no cleanup" fix would ship.
        """
        target, changed = snap_up(3 * 0.1, 0.1, 0, 0.001)
        self.assertEqual(repr(target), "0.3")
        self.assertFalse(changed)

    def test_a_quantity_between_two_steps_goes_up(self):
        """0.3 with a 0.25 step is 0.5, not 0.30 and not 0.25."""
        target, changed = snap_up(0.3, 0.25, 0, 0.001)
        self.assertEqual(target, 0.5)
        self.assertTrue(changed)

    def test_a_quantity_on_the_grid_is_left_alone(self):
        target, changed = snap_up(1.5, 0.5, 0, 0.001)
        self.assertEqual(target, 1.5)
        self.assertFalse(changed)

    def test_the_minimum_is_lifted_onto_the_step_grid(self):
        """A minimum of 0.3 on a 0.25 grid means 0.5 is the smallest order."""
        target, changed = snap_up(0.3, 0.25, 0.3, 0.001)
        self.assertEqual(target, 0.5)
        self.assertTrue(changed)

    def test_no_minimum_and_no_step_change_nothing(self):
        """The negative control: a shop that configured nothing sees nothing.

        The value comes back unchanged *and* unchanged is not the same as
        equal -- an identity check is what proves the module did not quietly
        rebuild the quantity on its way through.
        """
        for quantity in (1.0, 0.3, 7.25):
            target, changed = snap_up(quantity, 0, 0, 1.0)
            self.assertEqual(target, quantity)
            self.assertFalse(changed)
            self.assertIs(type(target), float)

    def test_a_removal_is_never_lifted_to_the_minimum(self):
        """Deleting a line must not buy five of it."""
        for quantity in (0.0, -1.0, -0.25):
            target, changed = snap_up(quantity, 1.0, 5.0, 1.0)
            self.assertEqual(target, quantity)
            self.assertFalse(changed)

    def test_the_grid_is_the_step_not_two_decimals(self):
        """A coarse UoM must not widen a fine step."""
        # Units round to 1: snapping 0.75 with a 0.25 step must still be 0.75,
        # i.e. the UoM rounding cleans the value but does not define the grid.
        target, _changed = snap_up(0.75, 0.25, 0, 1.0)
        self.assertEqual(target, 0.75)

    def test_a_quantity_is_told_apart_from_its_neighbours(self):
        self.assertTrue(is_on_grid(0.75, 0.25, 0.001))
        self.assertFalse(is_on_grid(0.8, 0.25, 0.001))

    def test_numbers_are_spelled_for_a_customer(self):
        self.assertEqual(format_quantity(5.0), "5")
        self.assertEqual(format_quantity(0.25), "0.25")
        self.assertEqual(format_quantity(1.5), "1.5")


class TestRuleResolution(TransactionCase):
    """Where a product's minimum and step come from."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env["product.public.category"]

    def _product(self, **values):
        values.setdefault("name", "Bulk Nuts")
        values.setdefault("type", "consu")
        values.setdefault("sale_ok", True)
        values.setdefault("list_price", 10.0)
        return self.env["product.template"].create(values)

    def test_a_product_without_a_value_inherits_its_category(self):
        category = self.Category.create({"name": "Boxes", "min_order_qty": 6, "qty_step": 6})
        product = self._product(public_categ_ids=[(6, 0, category.ids)])
        self.assertEqual(product._min_qty_rules(), (6.0, 6.0))

    def test_the_nearest_parent_category_answers_first(self):
        """A sub-category sets the step; the parent still supplies the minimum."""
        parent = self.Category.create({"name": "Wholesale", "min_order_qty": 12})
        child = self.Category.create({
            "name": "Wholesale / Nuts", "parent_id": parent.id, "qty_step": 2,
        })
        product = self._product(public_categ_ids=[(6, 0, child.ids)])
        self.assertEqual(product._min_qty_rules(), (12.0, 2.0))

    def test_the_product_beats_the_category(self):
        category = self.Category.create({"name": "Boxes", "min_order_qty": 6, "qty_step": 6})
        product = self._product(
            public_categ_ids=[(6, 0, category.ids)], min_order_qty=1, qty_step=0.25)
        self.assertEqual(product._min_qty_rules(), (1.0, 0.25))

    def test_the_two_columns_resolve_separately(self):
        """Minimum from the category, step from the product: both are used."""
        category = self.Category.create({"name": "Boxes", "min_order_qty": 6})
        product = self._product(public_categ_ids=[(6, 0, category.ids)], qty_step=2)
        self.assertEqual(product._min_qty_rules(), (6.0, 2.0))

    def test_a_variant_can_deviate_from_its_product(self):
        attribute = self.env["product.attribute"].create({
            "name": "Pack", "value_ids": [(0, 0, {"name": "Small"}), (0, 0, {"name": "Large"})],
        })
        product = self._product(
            min_order_qty=6, qty_step=6,
            attribute_line_ids=[(0, 0, {
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, attribute.value_ids.ids)],
            })],
        )
        self.assertEqual(len(product.product_variant_ids), 2)
        variant = product.product_variant_ids[0]
        self.assertEqual(variant._min_qty_rules(), (6.0, 6.0))
        variant.min_order_qty = 1
        self.assertEqual(variant._min_qty_rules(), (1.0, 6.0))
        # The sibling is untouched and the product still carries its own value.
        self.assertEqual(product.product_variant_ids[1]._min_qty_rules(), (6.0, 6.0))
        self.assertEqual(product.min_order_qty, 6.0)

    def test_the_uom_rounding_is_the_one_the_product_uses(self):
        """20.0 reads that precision from the "Product Unit" setting."""
        product = self._product()
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        self.assertAlmostEqual(product._min_qty_rounding(), 10.0 ** -precision)

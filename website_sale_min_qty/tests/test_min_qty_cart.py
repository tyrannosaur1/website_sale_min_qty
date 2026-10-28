# -*- coding: utf-8 -*-
"""The cart is where a step stops being a suggestion.

The assertions read the stored quantity back from the database: a value that
looks right in the ORM cache but was written as 0.7500000000000001 is exactly
the bug this module exists for.
"""
from odoo.tests.common import TransactionCase


class CartMinimumCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.partner = cls.env["res.partner"].create({"name": "Shop Customer"})

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def _product(self, **values):
        values.setdefault("name", "Bulk Nuts")
        values.setdefault("type", "consu")
        values.setdefault("sale_ok", True)
        values.setdefault("list_price", 10.0)
        return self.env["product.template"].create(values)

    def _order(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
        })

    def _variant_id(self, product):
        return product.product_variant_id.id

    def _stored_quantity(self, line):
        """The quantity as PostgreSQL has it, not as the cache shows it."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT product_uom_qty FROM sale_order_line WHERE id = %s", [line.id])
        return self.env.cr.fetchone()[0]

    # ------------------------------------------------------------------
    # Steps and float precision
    # ------------------------------------------------------------------
    def test_three_quarter_steps_total_exactly_0_75(self):
        product = self._product(qty_step=0.25)
        order = self._order()
        for _step in range(3):
            order._cart_update(product_id=self._variant_id(product), add_qty=0.25)
        line = order.order_line
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_uom_qty, 0.75)
        self.assertEqual(self._stored_quantity(line), 0.75)
        self.assertNotEqual(repr(self._stored_quantity(line)), "0.7500000000000001")

    def test_an_off_grid_quantity_is_rounded_up_in_the_cart(self):
        product = self._product(qty_step=0.25)
        order = self._order()
        result = order._cart_update(product_id=self._variant_id(product), add_qty=0.3)
        self.assertEqual(order.order_line.product_uom_qty, 0.5)
        self.assertIn("0.25", result["warning"])
        self.assertIn("0.5", result["warning"])

    def test_a_quantity_below_the_minimum_is_raised(self):
        product = self._product(min_order_qty=5)
        order = self._order()
        result = order._cart_update(product_id=self._variant_id(product), add_qty=1)
        self.assertEqual(order.order_line.product_uom_qty, 5.0)
        self.assertTrue(result["warning"])
        self.assertIn("minimum order quantity", result["warning"])

    def test_a_quantity_already_on_the_grid_is_not_touched(self):
        product = self._product(min_order_qty=5, qty_step=5)
        order = self._order()
        result = order._cart_update(product_id=self._variant_id(product), add_qty=10)
        self.assertEqual(order.order_line.product_uom_qty, 10.0)
        self.assertFalse(result["warning"])

    # ------------------------------------------------------------------
    # Removal and no-op
    # ------------------------------------------------------------------
    def test_a_line_can_still_be_removed(self):
        """The minimum must not turn "delete this line" into "buy five"."""
        product = self._product(min_order_qty=5)
        order = self._order()
        order._cart_update(product_id=self._variant_id(product), add_qty=5)
        line = order.order_line
        self.assertEqual(line.product_uom_qty, 5.0)
        order._cart_update(product_id=self._variant_id(product), line_id=line.id,
                           add_qty=None, set_qty=0)
        self.assertFalse(order.order_line)

    def test_no_rule_leaves_the_cart_alone(self):
        """Negative control: a product without a rule behaves like core."""
        product = self._product()
        self.assertEqual(product._min_qty_rules(), (0.0, 0.0))
        order = self._order()
        result = order._cart_update(product_id=self._variant_id(product), add_qty=7)
        self.assertEqual(order.order_line.product_uom_qty, 7.0)
        self.assertFalse(result["warning"])
        self.assertFalse(order._min_qty_violated_lines())

    # ------------------------------------------------------------------
    # Existing lines and the checkout check
    # ------------------------------------------------------------------
    def test_a_rule_change_does_not_rewrite_an_existing_line(self):
        product = self._product()
        order = self._order()
        order._cart_update(product_id=self._variant_id(product), add_qty=2)
        line = order.order_line
        product.min_order_qty = 5
        product.invalidate_recordset()
        self.assertEqual(line.product_uom_qty, 2.0)
        violated = order._min_qty_violated_lines()
        self.assertEqual(violated, line)
        # ... but the next change of quantity answers to the new rule.
        order._cart_update(product_id=self._variant_id(product), line_id=line.id,
                           set_qty=3)
        self.assertEqual(line.product_uom_qty, 5.0)
        self.assertFalse(order._min_qty_violated_lines())

    def test_a_line_off_the_step_grid_is_reported(self):
        product = self._product(qty_step=0.25)
        order = self._order()
        order._cart_update(product_id=self._variant_id(product), add_qty=0.25)
        line = order.order_line
        # Bypass the cart, the way a direct write or an old line would.
        line.product_uom_qty = 0.3
        self.assertEqual(order._min_qty_violated_lines(), line)

    def test_a_cart_with_no_rule_is_never_refused(self):
        product = self._product()
        order = self._order()
        order._cart_update(product_id=self._variant_id(product), add_qty=3)
        self.assertFalse(order._min_qty_violated_lines())

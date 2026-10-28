# Minimum Order Quantity & Purchase Steps

Sell by the box, the pallet or the quarter kilo: state the minimum and the multiple, and keep every add-to-cart path honest.

Odoo 16.0 – 20.0. One branch per series, the branch name is the series.

## What it does

- A minimum quantity and a step per product, per public category and per website; the strictest rule wins.
- The product page states the rule and pre-fills the quantity, so the customer sees the box size before typing a number.
- Every add-to-cart path is checked in one place: the product page, the quick add, the variant configurator and the combo selector.
- A quantity that does not match the step is snapped up to the next valid one, and the cart line says so.
- The rule is enforced on the server, so a hand-crafted POST cannot get around it.

## Install

1. Copy the module into your addons path.
2. Update the app list, install **Minimum Order Quantity & Purchase Steps**.
3. Sales › Products: set the minimum and the step on the product, its category, or the website.

## Translations

Chinese, Spanish, German, French, Italian, Dutch, Polish, Brazilian Portuguese and Russian ship with the module.

## License

OPL-1. See `LICENSE`.

## Support

Open an issue on this repository.

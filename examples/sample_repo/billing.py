"""A small billing module used to demonstrate program slicing.

Only `apply_discount` and its dependencies are causally relevant to the
target line used in run_demo.py. `send_welcome_email`, `format_receipt`,
and `log_audit_event` are unrelated noise that a full-file prompt would
waste tokens on, but that graph-based slicing correctly excludes.
"""

TAX_RATE = 0.08
LOYALTY_THRESHOLD = 500


def get_base_price(item_count, unit_price):
    subtotal = item_count * unit_price
    return subtotal


def get_loyalty_discount(customer_spend):
    if customer_spend > LOYALTY_THRESHOLD:
        rate = 0.15
    else:
        rate = 0.05
    return rate


def apply_discount(item_count, unit_price, customer_spend):
    subtotal = get_base_price(item_count, unit_price)
    discount_rate = get_loyalty_discount(customer_spend)
    discounted = subtotal * (1 - discount_rate)
    total_with_tax = discounted * (1 + TAX_RATE)
    return total_with_tax


def format_receipt(customer_name, total):
    header = f"Receipt for {customer_name}"
    footer = "Thank you for your purchase!"
    body = f"Total due: ${total:.2f}"
    return "\n".join([header, body, footer])


def send_welcome_email(customer_email):
    subject = "Welcome!"
    body = "Thanks for signing up."
    print(f"Emailing {customer_email}: {subject} - {body}")


def log_audit_event(event_name, payload):
    entry = {"event": event_name, "payload": payload}
    print(f"AUDIT: {entry}")


def unrelated_math_helper(x, y):
    z = x ** 2 + y ** 2
    return z ** 0.5

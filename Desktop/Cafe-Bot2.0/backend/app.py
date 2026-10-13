import json
import os
import secrets
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__, static_folder="../frontend", static_url_path="/")

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
_max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "512"))
_max_history_turns = int(os.getenv("ANTHROPIC_MAX_HISTORY_TURNS", "6"))
_tax_rate    = float(os.getenv("TAX_RATE",    "0.0"))   # e.g. 0.10 for 10 %
_delivery_fee = float(os.getenv("DELIVERY_FEE", "0.0"))  # flat fee per delivery order

_prompt_path = os.getenv("SYSTEM_PROMPT_PATH", "prompts/system-prompt.md")
with open(_prompt_path, encoding="utf-8") as _f:
    _system_prompt = _f.read()

_menu_path = os.getenv("MENU_PATH", "data/menu.json")
with open(_menu_path, encoding="utf-8") as _f:
    _menu_data = json.load(_f)

_menu_index: dict = {item["id"]: item for item in _menu_data.get("items", [])}

_promotions_path = os.getenv("PROMOTIONS_PATH", "data/promotions.json")
with open(_promotions_path, encoding="utf-8") as _f:
    _promotions_data = json.load(_f)

_promo_index: dict = {p["id"]: p for p in _promotions_data.get("promotions", [])}

_orders_path = os.getenv("ORDERS_PATH", "data/orders.json")


def _format_menu(menu_data):
    """Return a compact menu block to append to the system prompt."""
    category_labels = {
        "hot_drinks": "HOT DRINKS",
        "cold_drinks": "COLD DRINKS",
        "pastries":    "PASTRIES",
        "savoury":     "SAVOURY",
        "sweets":      "SWEETS",
    }
    by_category = {}
    for item in menu_data.get("items", []):
        if not item.get("available", True):
            continue
        by_category.setdefault(item.get("category", "other"), []).append(item)

    lines = [
        "\n---\n",
        "## AUTHORITATIVE MENU",
        "Only the items below exist. Never suggest items, prices, or sizes not on this list.\n",
    ]
    for cat in menu_data.get("categories", []):
        items = by_category.get(cat, [])
        if not items:
            continue
        lines.append(category_labels.get(cat, cat.upper()))
        for item in items:
            sizes = [s for s in item.get("sizes", []) if s.get("price_modifier", 0) != 0]
            if sizes:
                size_str = ", ".join(f"{s['label']} +${s['price_modifier']:.2f}" for s in sizes)
                lines.append(f"- {item['name']}: from ${item['price']:.2f} ({size_str})")
            else:
                lines.append(f"- {item['name']}: ${item['price']:.2f}")
        lines.append("")
    return "\n".join(lines)


def _format_promotions(promo_data: dict) -> str:
    active = [p for p in promo_data.get("promotions", []) if p.get("active")]
    if not active:
        return ""
    lines = [
        "\n---\n",
        "## ACTIVE PROMOTIONS",
        "Only the promotions listed here exist. Never invent or promise discounts not on this list.\n",
    ]
    for p in active:
        lines.append(f"**{p['name']}** ({p['id']}): {p['description']}")
        lines.append(f"  Rule: {p['rule']}\n")
    return "\n".join(lines)


_system_prompt = _system_prompt + _format_menu(_menu_data) + _format_promotions(_promotions_data)

# ── Session-based order state ─────────────────────────────────────────────────
_sessions: dict = {}


def _new_order() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "order_id": None,        # assigned only on confirmation, e.g. "ORD-A3F72C19"
        "status": "open",        # open | confirmed | cancelled
        "order_type": None,      # "dine_in" | "takeaway" | "delivery" | None
        "customer": {"name": None},
        "pickup_time": None,     # optional requested time, e.g. "10 minutes"
        "delivery": {            # populated only for delivery orders
            "phone": None, "address": None, "unit": None, "instructions": None,
        },
        "items": [],             # list of line-item dicts
        "promotion_id": None,
        "subtotal": 0.0,
        "discount": 0.0,
        "delivery_fee": 0.0,
        "tax": 0.0,
        "total": 0.0,
        "confirmed": False,
        "confirmed_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _get_or_create_order(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = _new_order()
    return _sessions[session_id]


def _format_order_context(order: dict) -> str:
    """Compact order-state block appended to the system prompt each request."""
    lines = ["\n---\n## CURRENT ORDER STATE"]
    if order.get("order_id"):
        lines.append(f"Order ID: {order['order_id']}")
    lines.append(f"Status: {order['status']}")
    if order["order_type"]:
        lines.append(f"Order type: {order['order_type']}")
    if order["customer"]["name"]:
        lines.append(f"Customer: {order['customer']['name']}")
    if order.get("pickup_time"):
        lines.append(f"Pickup time: {order['pickup_time']}")
    if order["order_type"] == "delivery":
        d = order.get("delivery", {})
        if d.get("phone"):        lines.append(f"Phone: {d['phone']}")
        if d.get("address"):      lines.append(f"Address: {d['address']}")
        if d.get("unit"):         lines.append(f"Unit: {d['unit']}")
        if d.get("instructions"): lines.append(f"Delivery instructions: {d['instructions']}")
    if order["items"]:
        lines.append("Items:")
        for idx, it in enumerate(order["items"], start=1):
            size  = f" ({it['size']})"    if it.get("size")  else ""
            notes = f" [{it['notes']}]"   if it.get("notes") else ""
            lines.append(f"  {idx}. {it['quantity']}x {it['name']}{size}{notes} — ${it['line_total']:.2f}")
        lines.append(f"Subtotal: ${order['subtotal']:.2f}")
        if order["discount"]:
            lines.append(f"Discount: -${order['discount']:.2f}")
        if order.get("delivery_fee"):
            lines.append(f"Delivery fee: ${order['delivery_fee']:.2f}")
        if order.get("tax"):
            lines.append(f"Tax: ${order['tax']:.2f}")
        lines.append(f"Total: ${order['total']:.2f}")
    else:
        lines.append("Items: none yet")
    if order["promotion_id"]:
        promo_name = _promo_index.get(order["promotion_id"], {}).get("name", order["promotion_id"])
        lines.append(f"Promotion applied: {promo_name} ({order['promotion_id']})")
    if order["confirmed"]:
        lines.append("Confirmed: yes")
    return "\n".join(lines)


# ── Promotion helpers ─────────────────────────────────────────────────────────

def _check_promo_eligibility(promo: dict, order: dict) -> bool:
    eligibility = promo.get("eligibility", {})
    now = datetime.now()

    allowed_days = eligibility.get("days", [])
    if allowed_days and now.strftime("%A") not in allowed_days:
        return False

    time_window = eligibility.get("time_window", {})
    if time_window:
        start_h, start_m = map(int, time_window["start"].split(":"))
        end_h,   end_m   = map(int, time_window["end"].split(":"))
        current = now.hour * 60 + now.minute
        if not (start_h * 60 + start_m <= current < end_h * 60 + end_m):
            return False

    if len(order["items"]) < eligibility.get("min_order_items", 0):
        return False

    required_cats = eligibility.get("required_categories", [])
    if required_cats:
        order_cats = {
            _menu_index[it["item_id"]]["category"]
            for it in order["items"]
            if it["item_id"] in _menu_index
        }
        if not all(cat in order_cats for cat in required_cats):
            return False

    required_ids = eligibility.get("required_item_ids", [])
    if required_ids:
        order_ids = {it["item_id"] for it in order["items"]}
        if not all(rid in order_ids for rid in required_ids):
            return False

    return True


def _calculate_discount(promo: dict, order: dict) -> float:
    info = promo.get("discount", {})
    dtype = info.get("type")
    if dtype == "percentage":
        target_cats = set(info.get("target_categories", []))
        eligible = sum(
            it["line_total"] for it in order["items"]
            if _menu_index.get(it["item_id"], {}).get("category") in target_cats
        )
        return round(eligible * info.get("value", 0) / 100, 2)
    if dtype == "fixed":
        return round(float(info.get("value", 0)), 2)
    return 0.0


def _apply_promotions(order: dict) -> None:
    """Set order[discount] and order[promotion_id]. Does not touch total."""
    if not order["items"]:
        order["promotion_id"] = None
        order["discount"] = 0.0
        return
    for promo in _promotions_data.get("promotions", []):
        if not promo.get("active", False):
            continue
        if _check_promo_eligibility(promo, order):
            order["promotion_id"] = promo["id"]
            order["discount"] = _calculate_discount(promo, order)
            return
    order["promotion_id"] = None
    order["discount"] = 0.0


def _recalculate_totals(order: dict) -> None:
    """Single source of truth for all price fields. Always call this after mutating items or order_type."""
    _apply_promotions(order)
    fee = _delivery_fee if order.get("order_type") == "delivery" else 0.0
    taxable = round(order["subtotal"] - order["discount"], 2)
    tax = round(taxable * _tax_rate, 2)
    order["delivery_fee"] = fee
    order["tax"] = tax
    order["total"] = round(taxable + fee + tax, 2)


def _promo_note(order: dict) -> str:
    pid = order.get("promotion_id")
    if not pid:
        return ""
    name = _promo_index.get(pid, {}).get("name", pid)
    return f" ({name} applied: −${order['discount']:.2f})"


# ── Add-item tool ─────────────────────────────────────────────────────────────
_add_item_tool = {
    "name": "add_item",
    "description": (
        "Add one menu item to the customer's current order. "
        "Only call this when the customer has clearly requested a specific item. "
        "Items with more than one size option require the 'size' field — "
        "if the customer has not stated a size, ask before calling this tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "The item's ID from the authoritative menu (e.g. 'd002').",
            },
            "size": {
                "type": "string",
                "description": "Size label exactly as listed in the menu (e.g. 'Medium'). Required when the item has more than one size option.",
            },
            "quantity": {
                "type": "integer",
                "description": "Number of this item to add. Defaults to 1.",
                "minimum": 1,
            },
            "notes": {
                "type": "string",
                "description": "Customization note for this item, e.g. 'oat milk', 'no sugar', 'extra shot'. Only set when the customer has explicitly requested it.",
            },
        },
        "required": ["item_id"],
    },
}


def _execute_add_item(tool_input: dict, order: dict) -> str:
    """Validate tool input against the live menu and mutate the order if valid."""
    item_id    = str(tool_input.get("item_id", "")).strip()
    size_label = tool_input.get("size")
    raw_qty    = tool_input.get("quantity", 1)
    raw_notes  = tool_input.get("notes")

    try:
        quantity = max(1, int(raw_qty))
    except (TypeError, ValueError):
        quantity = 1

    item = _menu_index.get(item_id)
    if not item:
        return f"'{item_id}' is not a valid menu item ID."
    if not item.get("available", True):
        return f"{item['name']} is not available right now."

    sizes = item.get("sizes", [])
    needs_size = len(sizes) > 1

    if needs_size and not size_label:
        opts = ", ".join(s["label"] for s in sizes)
        return f"Size is required for {item['name']}. Options: {opts}."

    if size_label:
        match = next((s for s in sizes if s["label"].lower() == str(size_label).lower()), None)
        if not match:
            opts = ", ".join(s["label"] for s in sizes)
            return f"'{size_label}' is not a valid size for {item['name']}. Options: {opts}."
        unit_price    = round(item["price"] + match["price_modifier"], 2)
        resolved_size = match["label"]
    else:
        unit_price    = item["price"]
        resolved_size = sizes[0]["label"] if sizes else None

    line_total = round(unit_price * quantity, 2)
    notes = str(raw_notes).strip()[:200] if raw_notes else None
    order["items"].append({
        "item_id":    item_id,
        "name":       item["name"],
        "size":       resolved_size,
        "quantity":   quantity,
        "unit_price": unit_price,
        "line_total": line_total,
        "notes":      notes,
    })
    order["subtotal"]   = round(sum(it["line_total"] for it in order["items"]), 2)
    _recalculate_totals(order)
    order["updated_at"] = datetime.now(timezone.utc).isoformat()

    size_str = f" ({resolved_size})" if resolved_size else ""
    return f"Added {quantity}x {item['name']}{size_str} at ${unit_price:.2f} each.{_promo_note(order)} Running total: ${order['total']:.2f}."


# ── Modify-item tool ──────────────────────────────────────────────────────────
_modify_item_tool = {
    "name": "modify_item",
    "description": (
        "Modify an existing item in the customer's current order. "
        "Use the 1-based line number shown in the order state. "
        "You may change quantity, size, or customization notes. "
        "Omit any field you are not changing. "
        "Size must be valid for that menu item."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "line_index": {
                "type": "integer",
                "description": "1-based position of the item in the order state list.",
                "minimum": 1,
            },
            "quantity": {
                "type": "integer",
                "description": "New quantity (minimum 1).",
                "minimum": 1,
            },
            "size": {
                "type": "string",
                "description": "New size label, exactly as listed in the menu (e.g. 'Large').",
            },
            "notes": {
                "type": "string",
                "description": "Customization note (e.g. 'oat milk', 'no sugar'). Replaces any existing note.",
            },
        },
        "required": ["line_index"],
    },
}


def _execute_modify_item(tool_input: dict, order: dict) -> str:
    """Validate and apply modifications to an existing order line item."""
    raw_idx = tool_input.get("line_index")
    try:
        line_index = int(raw_idx) - 1
    except (TypeError, ValueError):
        return "line_index must be a positive integer."

    items = order["items"]
    if not items:
        return "The order has no items to modify."
    if line_index < 0 or line_index >= len(items):
        return f"line_index {raw_idx} is out of range — the order has {len(items)} item(s)."

    line      = items[line_index]
    menu_item = _menu_index.get(line["item_id"])
    changed   = []

    new_qty = tool_input.get("quantity")
    if new_qty is not None:
        try:
            new_qty = max(1, int(new_qty))
        except (TypeError, ValueError):
            return "quantity must be a positive integer."
        line["quantity"] = new_qty
        changed.append(f"quantity → {new_qty}")

    new_size = tool_input.get("size")
    if new_size is not None:
        if menu_item is None:
            return f"Cannot validate size: '{line['item_id']}' is no longer on the menu."
        sizes = menu_item.get("sizes", [])
        match = next((s for s in sizes if s["label"].lower() == str(new_size).lower()), None)
        if not match:
            opts = ", ".join(s["label"] for s in sizes)
            return f"'{new_size}' is not a valid size for {line['name']}. Options: {opts}."
        line["size"]       = match["label"]
        line["unit_price"] = round(menu_item["price"] + match["price_modifier"], 2)
        changed.append(f"size → {match['label']}")

    new_notes = tool_input.get("notes")
    if new_notes is not None:
        line["notes"] = str(new_notes).strip()[:200]
        changed.append(f"notes → \"{line['notes']}\"")

    if not changed:
        return "No changes were specified."

    line["line_total"]  = round(line["unit_price"] * line["quantity"], 2)
    order["subtotal"]   = round(sum(it["line_total"] for it in items), 2)
    _recalculate_totals(order)
    order["updated_at"] = datetime.now(timezone.utc).isoformat()

    size_str = f" ({line['size']})" if line.get("size") else ""
    return (
        f"Updated line {raw_idx}: {line['quantity']}x {line['name']}{size_str} "
        f"at ${line['unit_price']:.2f} each (${line['line_total']:.2f}). "
        f"Changes: {', '.join(changed)}.{_promo_note(order)} Running total: ${order['total']:.2f}."
    )


# ── Remove-item tool ──────────────────────────────────────────────────────────
_remove_item_tool = {
    "name": "remove_item",
    "description": (
        "Remove an item from the customer's current order, or reduce its quantity. "
        "Use the 1-based line number shown in the order state. "
        "If 'quantity' is omitted, the entire line is removed. "
        "If 'quantity' is provided and is less than the current quantity, "
        "only that many units are removed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "line_index": {
                "type": "integer",
                "description": "1-based position of the item in the order state list.",
                "minimum": 1,
            },
            "quantity": {
                "type": "integer",
                "description": "Number of units to remove. Omit to remove the entire line.",
                "minimum": 1,
            },
        },
        "required": ["line_index"],
    },
}


def _execute_remove_item(tool_input: dict, order: dict) -> str:
    raw_idx = tool_input.get("line_index")
    try:
        line_index = int(raw_idx) - 1
    except (TypeError, ValueError):
        return "line_index must be a positive integer."

    items = order["items"]
    if not items:
        return "The order has no items to remove."
    if line_index < 0 or line_index >= len(items):
        return f"line_index {raw_idx} is out of range — the order has {len(items)} item(s)."

    line = items[line_index]
    remove_qty = tool_input.get("quantity")

    if remove_qty is not None:
        try:
            remove_qty = max(1, int(remove_qty))
        except (TypeError, ValueError):
            return "quantity must be a positive integer."

    if remove_qty is None or remove_qty >= line["quantity"]:
        removed_name = line["name"]
        items.pop(line_index)
        order["subtotal"] = round(sum(it["line_total"] for it in items), 2)
        _recalculate_totals(order)
        order["updated_at"] = datetime.now(timezone.utc).isoformat()
        return f"Removed {removed_name} from the order.{_promo_note(order)} Running total: ${order['total']:.2f}."

    line["quantity"] -= remove_qty
    line["line_total"] = round(line["unit_price"] * line["quantity"], 2)
    order["subtotal"] = round(sum(it["line_total"] for it in items), 2)
    _recalculate_totals(order)
    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    size_str = f" ({line['size']})" if line.get("size") else ""
    return (
        f"Reduced {line['name']}{size_str} to {line['quantity']}x "
        f"(${line['line_total']:.2f}).{_promo_note(order)} Running total: ${order['total']:.2f}."
    )


# ── Set-pickup-details tool ───────────────────────────────────────────────────
_set_pickup_details_tool = {
    "name": "set_pickup_details",
    "description": (
        "Save order-level details the customer has just provided: order type, name, or pickup time. "
        "Call this as soon as the customer gives any of these. "
        "For delivery orders also call set_delivery_details to store address and contact info. "
        "Include only the fields the customer has explicitly stated — omit everything else."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "order_type": {
                "type": "string",
                "enum": ["dine_in", "takeaway", "delivery"],
                "description": "How the customer wants to receive their order.",
            },
            "customer_name": {
                "type": "string",
                "description": "The customer's name for the order.",
            },
            "pickup_time": {
                "type": "string",
                "description": "When the customer wants to collect, e.g. '10 minutes' or '2:30 PM'. Optional.",
            },
        },
        "required": [],
    },
}


def _execute_set_pickup_details(tool_input: dict, order: dict) -> str:
    changed = []

    order_type = tool_input.get("order_type")
    if order_type in ("dine_in", "takeaway", "delivery"):
        order["order_type"] = order_type
        changed.append(f"order type → {order_type.replace('_', '-')}")

    customer_name = tool_input.get("customer_name")
    if customer_name:
        order["customer"]["name"] = str(customer_name).strip()[:100]
        changed.append(f"name → {order['customer']['name']}")

    pickup_time = tool_input.get("pickup_time")
    if pickup_time:
        order["pickup_time"] = str(pickup_time).strip()[:50]
        changed.append(f"pickup time → {order['pickup_time']}")

    if not changed:
        return "No pickup details were provided."

    _recalculate_totals(order)
    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    return f"Saved: {', '.join(changed)}."


# ── Set-delivery-details tool ─────────────────────────────────────────────────
_set_delivery_details_tool = {
    "name": "set_delivery_details",
    "description": (
        "Store delivery contact and address information for a delivery order. "
        "Only call this when order_type is 'delivery'. "
        "Include only fields the customer has explicitly stated — never guess or infer missing values."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "description": "Customer's phone number.",
            },
            "address": {
                "type": "string",
                "description": "Full street address including house/building number and street name.",
            },
            "unit": {
                "type": "string",
                "description": "Apartment, unit, or suite number if provided.",
            },
            "instructions": {
                "type": "string",
                "description": "Delivery instructions, e.g. 'leave at door' or 'ring bell'. Optional.",
            },
        },
        "required": [],
    },
}


def _execute_set_delivery_details(tool_input: dict, order: dict) -> str:
    if order.get("order_type") != "delivery":
        return "set_delivery_details can only be used for delivery orders."

    d = order.setdefault(
        "delivery",
        {"phone": None, "address": None, "unit": None, "instructions": None},
    )
    changed = []

    phone = tool_input.get("phone")
    if phone:
        safe_phone = "".join(c for c in str(phone) if c in "0123456789 +()-.")[:20]
        d["phone"] = safe_phone
        changed.append(f"phone → {d['phone']}")

    address = tool_input.get("address")
    if address:
        d["address"] = str(address).strip()[:200]
        changed.append(f"address → {d['address']}")

    unit = tool_input.get("unit")
    if unit:
        d["unit"] = str(unit).strip()[:50]
        changed.append(f"unit → {d['unit']}")

    instructions = tool_input.get("instructions")
    if instructions:
        d["instructions"] = str(instructions).strip()[:300]
        changed.append(f"instructions → {d['instructions']}")

    if not changed:
        return "No delivery details were provided."

    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    return f"Saved: {', '.join(changed)}."


# ── Confirm-order tool ────────────────────────────────────────────────────────
_confirm_order_tool = {
    "name": "confirm_order",
    "description": (
        "Finalise the customer's order. "
        "Only call this after you have shown the complete order summary AND the customer "
        "has replied with an explicit, unambiguous confirmation such as 'yes', 'confirm', "
        "'place it', or 'go ahead'. "
        "Never call this for vague replies ('ok', 'sure', 'sounds good', 'maybe', "
        "'I think so', or any reply that contains a question or a change request)."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def _execute_confirm_order(order: dict) -> str:
    if order["confirmed"]:
        return f"The order is already confirmed (ID: {order['order_id']})."
    if not order["items"]:
        return "Cannot confirm: the order has no items."
    if not order["order_type"]:
        return "Cannot confirm: order type (dine-in, takeaway, or delivery) is missing."
    if not order["customer"]["name"]:
        return "Cannot confirm: customer name is missing."
    if order["order_type"] == "delivery":
        d = order.get("delivery", {})
        missing = [f for f in ("phone", "address") if not d.get(f)]
        if missing:
            return f"Cannot confirm: delivery {' and '.join(missing)} is missing."

    now = datetime.now(timezone.utc).isoformat()
    order_id = "ORD-" + secrets.token_hex(4).upper()
    order["order_id"]    = order_id
    order["status"]      = "confirmed"
    order["confirmed"]   = True
    order["confirmed_at"] = now
    order["updated_at"]  = now

    _persist_order(order)
    return f"Order confirmed. ID: {order_id}."


def _persist_order(order: dict) -> None:
    try:
        with open(_orders_path, encoding="utf-8") as f:
            orders = json.load(f)
        if not isinstance(orders, list):
            orders = []
    except (FileNotFoundError, json.JSONDecodeError):
        orders = []
    orders.append(json.loads(json.dumps(order)))   # serialise-round-trip for a clean snapshot
    with open(_orders_path, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2, ensure_ascii=False)


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}

    message = data.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required"}), 400
    message = message.strip()[:2000]

    raw_history = data.get("history", [])
    if not isinstance(raw_history, list):
        raw_history = []

    max_messages = _max_history_turns * 2
    trimmed = raw_history[-max_messages:]

    safe_history = [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in trimmed
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]

    session_id = data.get("session_id", "")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = secrets.token_hex(16)
    session_id = session_id.strip()[:64]

    order = _get_or_create_order(session_id)
    messages = safe_history + [{"role": "user", "content": message}]

    try:
        _tools = [_add_item_tool, _modify_item_tool, _remove_item_tool,
                  _set_pickup_details_tool, _set_delivery_details_tool,
                  _confirm_order_tool]

        response = _client.messages.create(
            model=_model,
            max_tokens=_max_tokens,
            system=_system_prompt + _format_order_context(order),
            tools=_tools,
            messages=messages,
        )

        # Tool-use step: dispatch each tool call then ask Claude to respond
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "add_item":
                        result_text = _execute_add_item(block.input, order)
                    elif block.name == "modify_item":
                        result_text = _execute_modify_item(block.input, order)
                    elif block.name == "remove_item":
                        result_text = _execute_remove_item(block.input, order)
                    elif block.name == "set_pickup_details":
                        result_text = _execute_set_pickup_details(block.input, order)
                    elif block.name == "set_delivery_details":
                        result_text = _execute_set_delivery_details(block.input, order)
                    elif block.name == "confirm_order":
                        result_text = _execute_confirm_order(order)
                    else:
                        result_text = f"Unknown tool: {block.name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user",      "content": tool_results},
            ]
            response = _client.messages.create(
                model=_model,
                max_tokens=_max_tokens,
                system=_system_prompt + _format_order_context(order),
                tools=_tools,
                messages=messages,
            )

        reply_text = next(
            (block.text for block in response.content if hasattr(block, "text")),
            "",
        )
        return jsonify({
            "reply": reply_text,
            "session_id": session_id,
            "order": order,
        })
    except Exception:
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.get("/api/orders")
def get_orders():
    try:
        with open(_orders_path, encoding="utf-8") as f:
            orders = json.load(f)
        if not isinstance(orders, list):
            orders = []
    except (FileNotFoundError, json.JSONDecodeError):
        orders = []
    orders.sort(key=lambda o: o.get("confirmed_at", ""), reverse=True)
    return jsonify(orders)


@app.patch("/api/orders/<order_id>/status")
def update_order_status(order_id: str):
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip()
    _transitions = {
        "confirmed": ("preparing", "cancelled"),
        "preparing": ("ready",     "cancelled"),
        "ready":     ("completed",),
    }
    try:
        with open(_orders_path, encoding="utf-8") as f:
            orders = json.load(f)
        if not isinstance(orders, list):
            orders = []
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"error": "No orders found."}), 404

    for order in orders:
        if order.get("order_id") == order_id:
            current = order.get("status", "")
            if new_status not in _transitions.get(current, ()):
                return jsonify({"error": f"Cannot move '{current}' to '{new_status}'."}), 400
            order["status"]     = new_status
            order["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(_orders_path, "w", encoding="utf-8") as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)
            return jsonify(order)

    return jsonify({"error": "Order not found."}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(port=port, debug=debug)

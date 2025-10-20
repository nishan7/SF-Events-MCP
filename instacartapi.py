import os
import requests

INSTACART_API_KEY = os.getenv("INSTACART_API_KEY")  # your key
DEVELOPMENT_MODE = True

# endpoint base
if DEVELOPMENT_MODE:
    BASE_URL = "https://connect.dev.instacart.tools/idp/v1"
else:
    BASE_URL = "https://connect.instacart.com/idp/v1"

def create_recipe_page(title: str, image_url: str, ingredients: list, instructions: list, partner_linkback_url: str=None, enable_pantry_items: bool=False):
    """
    ingredients: list of dicts like:
      { "name": "whole milk", "display_text": "Whole milk", "measurements": [ { "quantity": 0.5, "unit": "cup" } ] }
    instructions: list of strings
    """
    url = f"{BASE_URL}/products/recipe"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {INSTACART_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "title": title,
        "image_url": image_url,
        "link_type": "recipe",
        "ingredients": ingredients,
        "instructions": instructions,
        "landing_page_configuration": {
            "enable_pantry_items": enable_pantry_items
        }
    }
    if partner_linkback_url:
        body["landing_page_configuration"]["partner_linkback_url"] = partner_linkback_url

    resp = requests.post(url, json=body, headers=headers)
    resp.raise_for_status()
    result = resp.json()
    return result.get("products_link_url")

if __name__ == "__main__":
    # Example for “Fish & Chips”
    title = "Fish and Chips"
    image_url = "https://example.com/fish-chips.jpg"
    ingredients = [
        { "name": "cod fillet", "display_text": "Cod fillet", "measurements": [ { "quantity": 500, "unit": "g" } ] },
        { "name": "potatoes", "display_text": "Potatoes", "measurements": [ { "quantity": 1, "unit": "kg" } ] },
        { "name": "vegetable oil", "display_text": "Vegetable oil", "measurements": [ { "quantity": 500, "unit": "ml" } ] },
        { "name": "tartar sauce", "display_text": "Tartar sauce", "measurements": [ { "quantity": 150, "unit": "ml" } ] },
        { "name": "lemon", "display_text": "Lemon", "measurements": [ { "quantity": 1, "unit": "large" } ] }
    ]
    instructions = [
        "Cut potatoes into fries and soak in cold water.",
        "Pat cod fillets dry and batter them.",
        "Heat oil to 180°C and fry fillets then fries until golden brown.",
        "Serve with tartar sauce and lemon wedges."
    ]
    try:
        link = create_recipe_page(title, image_url, ingredients, instructions, partner_linkback_url="https://yourapp.example/recipes/fish-chips", enable_pantry_items=True)
        print("Instacart link:", link)
    except Exception as e:
        print("Error creating recipe page:", e)
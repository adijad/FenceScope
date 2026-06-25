import os
import requests
from dotenv import load_dotenv


load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def autocomplete_address(query: str, limit: int = 5):
    """
    Real address autocomplete using Google Places API New.

    This works with arbitrary address input:
    "888"
    "1600 Penn"
    "860 University City Blvd"
    etc.
    """
    if not query or len(query.strip()) < 2:
        return []

    if not GOOGLE_MAPS_API_KEY:
        print("GOOGLE_MAPS_API_KEY is missing.")
        return []

    url = "https://places.googleapis.com/v1/places:autocomplete"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
    }

    body = {
        "input": query,
        "includedPrimaryTypes": ["street_address", "premise", "subpremise"],
        "includedRegionCodes": ["us"],
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        response.raise_for_status()

        data = response.json()
        suggestions = data.get("suggestions", [])[:limit]

        predictions = []

        for suggestion in suggestions:
            place_prediction = suggestion.get("placePrediction")

            if not place_prediction:
                continue

            description = (
                place_prediction.get("text", {}).get("text")
                or place_prediction.get("structuredFormat", {})
                .get("mainText", {})
                .get("text")
            )

            place_id = place_prediction.get("placeId")

            if description and place_id:
                predictions.append(
                    {
                        "description": description,
                        "place_id": place_id,
                    }
                )

        return predictions

    except requests.exceptions.HTTPError as error:
        print(f"Google Places API New autocomplete HTTP error: {error}")
        try:
            print(response.text)
        except Exception:
            pass
        return []

    except Exception as error:
        print(f"Autocomplete request failed: {error}")
        return []


def get_place_details(place_id: str):
    """
    Get formatted address and lat/lng from Google Place Details New.
    """
    if not place_id:
        return None

    if not GOOGLE_MAPS_API_KEY:
        print("GOOGLE_MAPS_API_KEY is missing.")
        return None

    url = f"https://places.googleapis.com/v1/places/{place_id}"

    headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "formattedAddress,location",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        formatted_address = data.get("formattedAddress")
        location = data.get("location", {})

        lat = location.get("latitude")
        lng = location.get("longitude")

        if not formatted_address or lat is None or lng is None:
            print("Place details response missing formattedAddress or location.")
            print(data)
            return None

        return {
            "display_name": formatted_address,
            "lat": float(lat),
            "lng": float(lng),
            "place_id": place_id,
            "type": "google_place_new",
        }

    except requests.exceptions.HTTPError as error:
        print(f"Google Place Details New HTTP error: {error}")
        try:
            print(response.text)
        except Exception:
            pass
        return None

    except Exception as error:
        print(f"Place details request failed: {error}")
        return None


def search_address(query: str, limit: int = 5):
    """
    Backward-compatible endpoint:
    autocomplete predictions + details for each prediction.
    """
    predictions = autocomplete_address(query, limit=limit)

    results = []

    for prediction in predictions:
        details = get_place_details(prediction["place_id"])

        if details:
            results.append(
                {
                    "display_name": details["display_name"],
                    "lat": details["lat"],
                    "lng": details["lng"],
                    "type": details["type"],
                    "importance": 1.0,
                }
            )

    return results
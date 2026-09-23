"""
Task Scheduler Agent — Field playbook
======================================
What to do, what not to do, and why - for every task the scheduler puts on
a farmer's day.

Three layers, applied in order and merged:

    1. category   - true for that kind of work on any farm
    2. crop       - what this crop specifically punishes you for
    3. situation   - what today's weather, soil or growth stage adds

Every "do not" carries its reason. A farmer follows a rule they understand
and ignores one they do not, so "do not spray above 30 C" is never written
without "the droplets evaporate before they land".

Sources: ICAR package-of-practices, FAO-56 and FAO-29, state agricultural
university extension bulletins, and pesticide label conventions (PHI/REI).
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ── Layer 1: by category ────────────────────────────────────────────────────

CATEGORY_PLAYBOOK: Dict[str, dict] = {

    "irrigation": {
        "do": [
            "Water early morning or evening - midday water is lost to evaporation before it reaches the roots.",
            "Check moisture at root depth first, not just the surface; the top 5 cm dries misleadingly fast.",
            "Walk the line once after starting and look for leaks, blocked drippers and dry patches.",
            "Stop when water has reached the root zone depth, not when the surface looks wet.",
        ],
        "do_not": [
            "Do not irrigate if heavy rain is expected within a day - the crop drowns and you pay for the water twice.",
            "Do not flood a field that is already at field capacity; roots starve of air within about 24 hours of waterlogging.",
            "Do not run sprinklers in wind above 15 km/h - half the water lands outside the field.",
            "Do not irrigate a mature crop that is drying down for harvest; it delays ripening and invites grain mould.",
        ],
    },

    "fertilization": {
        "do": [
            "Split nitrogen into 2-3 doses across the season - one large dose is mostly lost.",
            "Apply to moist soil, then irrigate lightly to move the nutrient into the root zone.",
            "Place fertilizer in a band beside the row, 5 cm away from the plant, not against the stem.",
            "Write down the product, quantity and date - next season's dose depends on this season's record.",
        ],
        "do_not": [
            "Do not apply before heavy rain - nitrate moves below the roots and reaches the groundwater.",
            "Do not broadcast urea on a dry, hot surface; up to a third is lost to the air as ammonia within days.",
            "Do not apply to a waterlogged or frozen field - none of it gets in, and it runs off with the first water.",
            "Do not put fertilizer in contact with seed or stem; the salt burns roots and kills seedlings.",
        ],
    },

    "pest_control": {
        "do": [
            "Identify the pest before you spray - the wrong chemical costs money and kills the natural enemies that were helping.",
            "Spray early morning or late evening, when pollinators are not foraging and the droplet does not evaporate.",
            "Wear gloves, goggles and a mask, and stand so the wind carries spray away from you.",
            "Cover the underside of the leaves; most sucking pests and fungal spores are there, not on top.",
            "Rotate the chemical group between sprays so the pest does not become resistant.",
            "Keep the label, and note the lot number and date.",
        ],
        "do_not": [
            "Do not spray within the pre-harvest interval on the label - residue above the limit makes the produce unsellable and unsafe.",
            "Do not spray above 30 C or in wind above 15 km/h; the droplets evaporate or drift onto a neighbour's field.",
            "Do not let anyone re-enter the field before the re-entry interval has passed - the residue on the leaves is still strong enough to make a person ill.",
            "Do not mix products unless the label says the mixture is safe - some combinations burn the crop.",
            "Do not spray a crop in flower with an insecticide toxic to bees; you lose the pollination you need for fruit set.",
            "Do not wash the sprayer or dump leftover mix near a well, canal or pond.",
        ],
    },

    "soil_preparation": {
        "do": [
            "Work the soil at the right moisture - it should crumble in the hand, not smear.",
            "Keep tillage shallow where you can; deep repeated tillage burns organic matter and forms a hard pan.",
            "Level the field so water spreads evenly; an uneven field wastes water at both ends.",
            "Mix crop residue or compost in ahead of time so it has weeks to break down.",
        ],
        "do_not": [
            "Do not till wet soil - it compacts into clods that no later operation can fix, especially in black cotton soil.",
            "Do not burn crop residue; it destroys the organic matter and nitrogen the next crop needs.",
            "Do not work fine soil into dust - the first rain seals the surface and the seedling cannot emerge.",
        ],
    },

    "planting": {
        "do": [
            "Use certified seed and check the germination rate before deciding seed quantity.",
            "Treat seed against soil-borne disease before sowing.",
            "Sow at the depth the crop needs - too deep and the seedling exhausts itself before reaching light.",
            "Sow when soil moisture is adequate for germination, ideally with rain or irrigation to follow.",
            "Keep row spacing right: crowding costs more yield than a slightly thin stand.",
        ],
        "do_not": [
            "Do not sow into dry soil hoping for rain - the seed germinates on a light shower and then dies before the next one.",
            "Do not sow when frost is forecast within the emergence window - seedlings do not recover.",
            "Do not save seed from a hybrid crop; the next generation does not perform like the parent.",
            "Do not put starter fertilizer in the furrow touching the seed; the salt burns the emerging root and thins the stand.",
        ],
    },

    "harvesting": {
        "do": [
            "Check maturity by the crop's own indicators - grain moisture, pod colour, tuber skin set - not by the calendar alone.",
            "Harvest in a dry spell, and dry the produce to safe storage moisture before it goes into a bag.",
            "Line up labour, machinery and transport a day ahead; a harvest that stops half-way loses grade.",
            "Keep produce off bare ground and out of the sun after cutting.",
        ],
        "do_not": [
            "Do not harvest wet produce into storage - it heats, moulds and can produce aflatoxin.",
            "Do not delay past maturity; grain shatters, pods split, and quality falls every day.",
            "Do not harvest before the pre-harvest interval of the last spray has passed - the residue makes the produce unsafe and the lot can be rejected.",
        ],
    },

    "monitoring": {
        "do": [
            "Walk a fixed pattern across the field, not just the edge - problems start in the middle where you do not go.",
            "Check the underside of leaves and the base of the stem.",
            "Photograph anything unusual, with a leaf or a coin for scale, before you treat it.",
            "Count rather than guess - 'ten aphids on five plants' decides a spray; 'some aphids' does not.",
        ],
        "do_not": [
            "Do not move between fields without cleaning footwear when disease is present; you carry the spores to the clean field yourself.",
            "Do not spray on the strength of one damaged plant; check whether it is spreading first.",
        ],
    },

    "pruning": {
        "do": [
            "Sterilise the blade between trees - a wipe of spirit or dilute bleach.",
            "Cut just outside the branch collar so the wound closes over.",
            "Remove dead, diseased and crossing wood first; often that is all that is needed.",
            "Take prunings out of the orchard and destroy diseased wood.",
        ],
        "do_not": [
            "Do not prune in wet weather - open cuts in humidity are how canker and gummosis get in.",
            "Do not remove more than about a quarter of the canopy in one season; the tree responds with weak water shoots.",
            "Do not leave stubs or tear the bark - a torn wound does not close and becomes the entry point for rot.",
        ],
    },

    "weeding": {
        "do": [
            "Weed early - the first 30-45 days after sowing decide how much yield weeds take.",
            "Remove weeds before they set seed; one season of seeding is several seasons of weeding.",
            "Use mulch or close spacing to suppress weeds instead of repeated chemical use.",
        ],
        "do_not": [
            "Do not hoe deep near the crop row; the feeder roots are shallow and close in.",
            "Do not let herbicide drift onto a neighbouring crop.",
            "Do not use the same herbicide season after season - the weeds become resistant.",
        ],
    },

    "market_action": {
        "do": [
            "Confirm today's price at the mandi before loading; quotes move between morning and afternoon.",
            "Grade and clean the produce first - a grade step usually pays more than it costs.",
            "Carry weighing receipts and keep your own record of what left the farm.",
        ],
        "do_not": [
            "Do not transport on a single quote from one buyer, because the price can change before you arrive and you cannot take the load home.",
            "Do not sell wet or ungraded produce in a glut; it sets the lowest price of the day.",
        ],
    },

    "other": {
        "do": ["Note what you did, when, and what it cost - the record is what makes next season better."],
        "do_not": [],
    },
}


# ── Layer 2: by crop ────────────────────────────────────────────────────────
#
# Only the things this crop specifically punishes. Keys are the canonical
# crop names the other FarmXpert agents use.

CROP_PLAYBOOK: Dict[str, Dict[str, dict]] = {

    "rice": {
        "irrigation": {
            "do": ["Keep 5 cm standing water from tillering to grain filling, and drain at physiological maturity."],
            "do_not": ["Do not let the field dry and crack during flowering - the panicle sets fewer grains and does not recover."],
        },
        "fertilization": {
            "do_not": ["Do not top-dress urea into deep standing water; drain to a thin film, apply, then re-flood."],
        },
    },

    "wheat": {
        "irrigation": {
            "do": ["Never miss the crown-root-initiation irrigation about 21 days after sowing - it sets the number of tillers."],
            "do_not": ["Do not irrigate heavily when the grain is filling and wind is expected; a wet, top-heavy crop lodges."],
        },
    },

    "cotton": {
        "pest_control": {
            "do": ["Scout for pink bollworm with pheromone traps and act on the trap count, not on the calendar."],
            "do_not": ["Do not spray broad-spectrum insecticide early in the season; it wipes out the predators that control whitefly and aphid later."],
        },
        "irrigation": {
            "do_not": ["Do not over-irrigate during vegetative growth - the plant makes leaf instead of bolls."],
        },
    },

    "groundnut": {
        "irrigation": {
            "do": ["Protect the pegging and pod-filling stage above all - water stress there is a direct loss of pods."],
            "do_not": ["Do not irrigate heavily just before harvest; wet pods at lifting are how aflatoxin starts."],
        },
        "fertilization": {
            "do": ["Apply gypsum at pegging for calcium - groundnut takes it up through the pod, not the root."],
            "do_not": ["Do not apply heavy nitrogen; groundnut fixes its own and extra nitrogen grows leaf at the cost of pods."],
        },
    },

    "sugarcane": {
        "irrigation": {
            "do": ["Protect the grand growth period; this is where the season's cane weight is made."],
        },
        "harvesting": {
            "do": ["Cut and deliver to the mill within 24 hours - sugar recovery falls every hour after cutting."],
        },
    },

    "potato": {
        "pest_control": {
            "do": ["Watch for late blight whenever nights are cool and leaves stay wet; a preventive spray beats a curative one."],
        },
        "irrigation": {
            "do_not": ["Do not let the soil swing between dry and wet during tuber bulking - that is what causes hollow heart and cracking."],
        },
        "harvesting": {
            "do": ["Kill the haulm 10-15 days before lifting so the skin sets and the tubers do not scuff."],
        },
    },

    "tomato": {
        "irrigation": {
            "do_not": ["Do not water irregularly during fruiting - uneven moisture with low calcium causes blossom-end rot."],
        },
        "pest_control": {
            "do": ["Stake and prune for airflow; a dense canopy is what keeps leaves wet long enough for blight."],
        },
    },

    "maize": {
        "irrigation": {
            "do": ["Tasselling and silking are the critical stages - stress for even a few days there cuts the cob directly."],
        },
    },

    "soybean": {
        "fertilization": {
            "do": ["Inoculate the seed with rhizobium; it replaces most of the nitrogen dose."],
            "do_not": ["Do not apply heavy nitrogen - it suppresses the nodules that fix it for free."],
        },
    },

    "mustard": {
        "pest_control": {
            "do": ["Check for aphid from flowering onward; a heavy infestation at pod fill is the usual cause of loss."],
        },
    },

    "onion": {
        "irrigation": {
            "do_not": ["Stop irrigation 15-20 days before harvest - bulbs lifted wet do not store."],
        },
    },

    "mango": {
        "pruning": {
            "do": ["Prune right after harvest so the new flush has time to mature before flowering."],
            "do_not": ["Do not prune close to flowering - you cut off next season's crop."],
        },
        "irrigation": {
            "do_not": ["Do not irrigate during the flower-bud stress period; the dry spell is what triggers flowering."],
        },
    },

    "banana": {
        "irrigation": {
            "do": ["Banana needs water almost continuously - it has shallow roots and a large leaf area."],
        },
    },

    "cabbage": {
        "irrigation": {
            "do_not": ["Do not swing between dry and heavy watering during head formation - the heads split."],
        },
    },

    # These four are crops the crop predictor can actually recommend for
    # Gujarat. Without an entry here the scheduler fell back to generic advice
    # for a crop the model had just told the farmer to sow.
    "guar": {
        "irrigation": {
            "do": ["Guar is grown rainfed in most of Gujarat; one irrigation at flowering is usually all it needs."],
            "do_not": ["Do not let water stand, even briefly - guar collapses from root rot far more often than from drought."],
        },
        "fertilization": {
            "do": ["Inoculate the seed; guar fixes its own nitrogen."],
            "do_not": ["Do not apply heavy nitrogen - it grows haulm instead of pods and delays maturity."],
        },
    },

    "coriander": {
        "irrigation": {
            "do": ["For leaf, keep the soil evenly moist and pick often; for seed, reduce water as the crop matures."],
            "do_not": ["Do not irrigate at seed set - wet weather then shrivels the seed and dulls its colour."],
        },
        "harvesting": {
            "do": ["Cut the seed crop when the fruit turns brown but before it shatters, and dry in shade to keep the aroma."],
        },
    },

    "ajwain": {
        "irrigation": {
            "do": ["Two or three light irrigations usually carry the whole crop."],
            "do_not": ["Do not water near seed maturity; rain or irrigation then stains and splits the seed."],
        },
        "fertilization": {
            "do_not": ["Do not push nitrogen - it delays maturity and brings aphid."],
        },
    },

    "white peas": {
        "irrigation": {
            "do": ["Protect flowering and pod filling; the rest of the season needs very little."],
            "do_not": ["Do not let water stand at any stage - white peas do not tolerate waterlogging."],
        },
        "harvesting": {
            "do": ["Harvest when pods are dry and firm; over-dry pods shatter during threshing."],
        },
    },

    "chickpea": {
        "irrigation": {
            "do_not": ["Do not over-irrigate; chickpea is a dryland crop and wet soil brings wilt and root rot."],
        },
    },
}


# ── Layer 3: by situation ───────────────────────────────────────────────────
#
# Added when the day's conditions, the soil or the growth stage call for it.
# Keys are used by the engine; the text is what the farmer reads.

SITUATION_NOTES: Dict[str, str] = {
    "heat_day":        "Start at first light and stop by 11 am - the afternoon will be dangerously hot for anyone working in the open. Drink water every half hour.",
    "heat_danger":     "Conditions are dangerous for outdoor work today. Move everything you can to early morning, and do not send anyone into the field alone at midday.",
    "frost_night":     "Frost is likely tonight. Light irrigation in the evening, or smoke on the windward edge, raises the canopy temperature by a degree or two.",
    "frozen_ground":   "The ground is frozen. Water will not go in and machinery will damage the structure - wait for a thaw.",
    "gale_wind":       "Winds are strong enough to be unsafe in the open. Postpone anything overhead, on a ladder, or with a sprayer.",
    "wet_field":       "The field is too wet for machinery. Working it now compacts the soil and the damage lasts for seasons.",
    "rain_coming":     "Rain is expected. Anything that must stay dry to work should wait for the next clear window.",
    "saline_soil":     "This soil is salty. Irrigate a little extra to push salt below the roots, and never let the soil dry out fully between waterings.",
    "acid_soil":       "This soil is acidic. Phosphorus you apply will be locked up until it is limed.",
    "critical_stage":  "The crop is at a stage where stress cannot be made up later. Do not let this slip.",
    "near_harvest":    "Harvest is close. Check the pre-harvest interval of any spray before you use it.",
    "low_moisture":    "Soil moisture is low at root depth. Irrigation here is not optional.",
    "waterlogged":     "The root zone is saturated. Open the drains first; roots suffocate within about a day.",
}


# ── Assembly ────────────────────────────────────────────────────────────────

def build_guidance(category: str,
                   crop: Optional[str] = None,
                   situations: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Merge the three layers into the do / do-not lists shown on a task.

    Crop advice comes first: it is the most specific thing the farmer needs
    to hear, and it is the part that differs from what they already know.
    """
    base = CATEGORY_PLAYBOOK.get(category) or CATEGORY_PLAYBOOK["other"]
    do: List[str] = []
    do_not: List[str] = []

    crop_key = (crop or "").strip().lower()
    crop_rules = CROP_PLAYBOOK.get(crop_key, {}).get(category, {})
    do.extend(crop_rules.get("do", []))
    do_not.extend(crop_rules.get("do_not", []))

    do.extend(base.get("do", []))
    do_not.extend(base.get("do_not", []))

    for key in situations or []:
        note = SITUATION_NOTES.get(key)
        if note and note not in do:
            do.append(note)

    return {"do": _dedupe(do), "do_not": _dedupe(do_not)}


def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def known_crops() -> List[str]:
    """Crops with specific advice beyond the general category rules."""
    return sorted(CROP_PLAYBOOK)

"""
OKF bundle builder
===================
Renders the Open Knowledge Format bundle that the retrieval agent reads.

Run it after changing an agent's crop configuration:

    python -m AI_Backend.knowledge.build_okf

Why generate rather than hand-write: the numbers a farmer is told - the pH a
crop wants, its critical stages, its salt tolerance - already exist inside the
agents that compute with them. Writing them a second time in Markdown would
guarantee the two disagree within a season. So every fact here is READ from
the agent configs, and only the prose around it is authored.

Each crop document therefore has two parts:

  * facts     rendered from soil_health, irrigation_planner and task_scheduler
              configs. Change a config, re-run this, and the handbook follows.
  * guidance  curated prose below, written once, about things no config holds:
              what the crop punishes you for, and what a farmer should watch.

The output is clean Markdown with one idea per heading, which is also what
makes it good input for the vector indexer (see retrieval_agent/indexer.py).
"""

from __future__ import annotations

import json
import pathlib
from datetime import date
from typing import Any, Dict, List

BUNDLE_DIR = pathlib.Path(__file__).resolve().parent / "okf"


# ── curated prose, one entry per crop ───────────────────────────────────────
# Sources: ICAR package of practices, state agricultural university extension
# bulletins (Gujarat, Punjab, Maharashtra), FAO-56 and FAO-29.

CROP_NOTES: Dict[str, Dict[str, Any]] = {
    "groundnut": {
        "season": "Kharif (June-July sowing); summer crop under irrigation",
        "tags": ['aflatoxin', 'pegging', 'gypsum', 'leaf spot', 'white grub', 'pod rot'],
        "display": "Groundnut",
        "family": "Oilseed legume",
        "summary": "Pegging and pod filling decide the crop; calcium reaches the pod directly, not through the root.",
        "water": ["Pegging and pod filling are the stages that set pod number. Stress there is a direct loss that later watering cannot recover.",
                  "Stop irrigating before harvest. Pods lifted wet are how aflatoxin contamination starts, and a contaminated lot is unsellable."],
        "nutrition": ["It fixes its own nitrogen. Heavy nitrogen grows leaf at the cost of pods.",
                      "Calcium is the nutrient to watch: the pod absorbs it directly from the soil around it, so a deficiency shows as empty or poorly filled shells."],
        "soil": ["Well-drained sandy loam suits it. On heavy waterlogged soil, pod rot follows."],
        "problems": ["Leaf spot and rust in humid spells; scout from 40 days after sowing.",
                     "White grub in sandy soils - treat the seed, do not wait for wilting plants."],
        "harvest": ["Lift when the inner shell shows dark veining and about three quarters of pods are mature.",
                    "Dry to safe storage moisture before bagging; heat in a wet bag is what produces aflatoxin."],
    },
    "wheat": {
        "season": "Rabi (November-December sowing)",
        "tags": ['crown root initiation', 'yellow rust', 'lodging', 'tillering'],
        "display": "Wheat", "family": "Cereal",
        "summary": "The crown root irrigation about 21 days after sowing sets tiller number and the season's yield.",
        "water": ["Never miss the crown-root-initiation irrigation, about 21 days after sowing. It decides how many tillers the crop carries.",
                  "Flowering and grain filling are the other two stages that cannot be missed."],
        "nutrition": ["Split nitrogen: at sowing, at crown root initiation, and at maximum tillering."],
        "soil": ["Prefers well-drained loam. Waterlogging for even a day at tillering shows up as yellowing and lost tillers."],
        "problems": ["Yellow rust in cool humid weather - scout the lower leaves from tillering.",
                     "Heavy irrigation with wind during grain filling lays the crop flat and costs both yield and harvest speed."],
        "harvest": ["Physiological maturity is when filling stops, but the grain is still about 30 percent moisture - too wet to combine or store. Wait until it hardens to roughly 14 percent, or harvest wetter and dry it down.",
                    "Do not leave a ripe crop standing. Every extra day risks lodging, rain, hail and shrivelled grain, and a lodged crop is far slower to cut."],
    },
    "rice": {
        "season": "Kharif (transplanted June-July)",
        "tags": ['blast', 'bacterial leaf blight', 'stem borer', 'puddling', 'standing water'],
        "display": "Rice (paddy)", "family": "Cereal",
        "summary": "Water depth is the management tool: keep a shallow layer, and drain at maturity.",
        "water": ["Keep about 5 cm of standing water from tillering to grain filling.",
                  "Do not let the field dry and crack at flowering: the panicle sets fewer grains and does not recover.",
                  "Drain at physiological maturity so the field is firm for harvest and the grain dries evenly."],
        "nutrition": ["Urea broadcast into deep standing water is largely lost to the water itself rather than taken up by the crop."],
        "soil": ["Puddled clay holds water best. On light soil the water cost is much higher."],
        "problems": ["Blast and bacterial leaf blight in humid weather; avoid excess nitrogen, which makes both worse.",
                     "Stem borer - watch for dead hearts, act on trap counts rather than the calendar."],
        "harvest": ["Harvest at about 20 percent grain moisture and dry down; over-dry grain breaks during milling."],
    },
    "cotton": {
        "season": "Kharif (May-June sowing), long duration",
        "tags": ['pink bollworm', 'whitefly', 'boll', 'square', 'reddening'],
        "display": "Cotton", "family": "Fibre",
        "summary": "Square and boll formation decide yield; early broad-spectrum sprays cost more than they save.",
        "water": ["Flowering and boll development are the stages that set yield; protect those two above all."],
        "nutrition": ["Potassium matters at boll filling; a deficiency shows as reddening leaves and small bolls."],
        "soil": ["Deep black cotton soil suits it, but it must drain: cotton does not tolerate standing water."],
        "problems": ["Pink bollworm: use pheromone traps and act on the trap count, not on a spray calendar.",
                     "Whitefly and aphid outbreaks late in the season are usually caused by earlier spraying, not by the weather."],
        "harvest": ["Pick dry, and keep picks separate by grade. Damp cotton stains and loses a grade in storage."],
    },
    "maize": {
        "season": "Kharif and rabi",
        "tags": ['fall armyworm', 'tasselling', 'silking', 'stalk rot', 'black layer'],
        "display": "Maize", "family": "Cereal",
        "summary": "Tasselling and silking are the two weeks that decide the cob.",
        "water": ["Tasselling and silking are the critical stages; stress for even a few days there cuts cob weight directly."],
        "nutrition": ["A heavy nitrogen feeder. Split the dose and place it beside the row, not against the stem."],
        "soil": ["Well-drained loam. It is sensitive to waterlogging at the seedling stage."],
        "problems": ["Fall armyworm: scout whorls early; an infestation found late is far harder to treat.",
                     "Stalk rot follows water stress at grain filling."],
        "harvest": ["Harvest when the black layer forms at the kernel base and husks are dry."],
    },
    "sugarcane": {
        "season": "Planted October-November or February-March; 12-18 month crop",
        "tags": ['grand growth', 'borer', 'lodging', 'sugar recovery', 'ratoon'],
        "display": "Sugarcane", "family": "Long-duration cash crop",
        "summary": "The grand growth period makes the season's weight; sugar starts falling the hour it is cut.",
        "water": ["Protect the grand growth period above all: this is where cane weight is made.",
                  "It is a long, thirsty crop - plan the water for the whole season, not for one month."],
        "nutrition": ["Earthing up with the nitrogen dose supports the cane and reduces lodging."],
        "soil": ["Deep, well-drained soil with good organic matter. It tolerates neither waterlogging nor drought for long."],
        "problems": ["Borers through the season; remove and destroy affected canes rather than spraying blind.",
                     "Lodged cane loses weight and is far more expensive to cut."],
        "harvest": ["Cut and deliver to the mill within 24 hours. Sugar recovery falls every hour after cutting."],
    },
    "soybean": {
        "season": "Kharif (June-July sowing)",
        "tags": ['yellow mosaic', 'girdle beetle', 'semilooper', 'rhizobium', 'shattering'],
        "display": "Soybean", "family": "Oilseed legume",
        "summary": "Inoculate the seed and keep nitrogen low; pod filling is the stage to protect.",
        "water": ["Flowering and pod filling are critical. Waterlogging at either is as damaging as drought."],
        "nutrition": ["Inoculate seed with rhizobium; it replaces most of the nitrogen dose.",
                      "Heavy nitrogen suppresses the nodules that would have fixed it for free."],
        "soil": ["Well-drained loam; it will not tolerate standing water for long."],
        "problems": ["Girdle beetle and semilooper; scout weekly through vegetative growth.",
                     "Yellow mosaic virus spreads by whitefly - control the vector, not the symptom."],
        "harvest": ["Harvest as soon as pods rattle; delay and the pods shatter in the field."],
    },
    "potato": {
        "season": "Rabi (October-November planting)",
        "tags": ['late blight', 'hollow heart', 'haulm', 'tuber bulking', 'curing'],
        "display": "Potato", "family": "Tuber",
        "summary": "Steady moisture during bulking, and a killed haulm before lifting.",
        "water": ["Keep moisture steady through tuber bulking. A dry spell followed by heavy watering makes the tuber grow in a burst, which is what causes hollow heart and growth cracks.",
                  "Stop irrigation before lifting so the soil is friable and the skin sets."],
        "nutrition": ["Potassium is heavily used. Excess nitrogen delays bulking and grows haulm."],
        "soil": ["Loose, well-drained loam. Clods at planting mean misshapen tubers."],
        "problems": ["Late blight whenever nights are cool and leaves stay wet: a preventive spray beats a curative one.",
                     "Do not plant into cold wet soil; seed pieces rot before they sprout."],
        "harvest": ["Kill the haulm 10-15 days before lifting so the skin sets and tubers do not scuff.",
                    "Cure in shade before storage; tubers stored warm and damp rot."],
    },
    "tomato": {
        "season": "Kharif, rabi and summer",
        "tags": ['blossom end rot', 'early blight', 'late blight', 'fruit borer', 'staking'],
        "display": "Tomato", "family": "Vegetable",
        "summary": "Even moisture prevents blossom-end rot; an open canopy prevents blight.",
        "water": ["Blossom-end rot is almost always a watering fault, not a calcium shortage. Buying calcium spray will not fix an irregular irrigation schedule."],
        "nutrition": ["Calcium availability depends on steady water. Liming an acid soil helps; erratic irrigation undoes it."],
        "soil": ["Well-drained loam, pH 6.0-7.0. It is moderately sensitive to salt."],
        "problems": ["Early and late blight: stake and prune for airflow, because a dense canopy keeps leaves wet long enough to infect.",
                     "Fruit borer - scout and hand-pick early; it is far cheaper than a late spray programme."],
        "harvest": ["Pick at breaker stage for distant markets, ripe for local sale."],
    },
    "mango": {
        "season": "Perennial; flowering December-February, harvest April-June",
        "tags": ['hopper', 'powdery mildew', 'fruit fly', 'flowering', 'sap burn', 'alternate bearing'],
        "display": "Mango (orchard)", "family": "Perennial fruit",
        "summary": "A dry spell triggers flowering; pruning is timed to the flush, not the calendar.",
        "water": ["Do not irrigate during the flower-bud stress period: the dry spell is what triggers flowering.",
                  "Water steadily during fruit development, then reduce before harvest."],
        "nutrition": ["Feed after harvest, when the tree is building the next season's flush."],
        "soil": ["Deep, well-drained soil. It will not tolerate a high water table."],
        "problems": ["Hopper and powdery mildew at flowering are the classic causes of a failed set.",
                     "Fruit fly near maturity - use traps and collect fallen fruit rather than spraying the canopy."],
        "harvest": ["Harvest with a stalk attached to avoid sap burn on the skin."],
    },
    "cabbage": {
        "season": "Rabi (September-November transplanting)",
        "tags": ['head splitting', 'club root', 'diamondback moth', 'boron', 'hollow stem', 'whiptail'],
        "display": "Cabbage", "family": "Vegetable (brassica)",
        "summary": "Head formation is the critical stage; uneven watering splits heads.",
        "water": ["Do not swing between dry and heavy watering during head formation - the heads split and lose all market value."],
        "nutrition": ["Boron deficiency causes hollow stem and molybdenum deficiency causes whiptail on acid soils; lime and apply borax where needed."],
        "soil": ["Fertile, well-drained loam with steady moisture; it is a shallow-rooted, hungry crop."],
        "problems": ["Diamondback moth resists many products - rotate chemical groups and use biological options early.",
                     "Aphids inside a forming head cannot be reached by a spray; act before heading."],
        "harvest": ["Cut when heads are firm. A head left past maturity splits after the next irrigation or rain."],
    },
    "onion": {
        "season": "Rabi and kharif",
        "tags": ['thrips', 'purple blotch', 'bulb', 'curing', 'neck fall', 'sulphur'],
        "display": "Onion", "family": "Vegetable (bulb)",
        "summary": "Stop water before lifting, or the crop will not store.",
        "water": ["Stop irrigation 15-20 days before harvest. Bulbs lifted wet do not store, whatever the curing."],
        "nutrition": ["Sulphur affects pungency and storage life; it is often the missing nutrient."],
        "soil": ["Well-drained loam. A shallow root system means it cannot chase water deep."],
        "problems": ["Thrips in dry weather - check leaf axils, where they hide.",
                     "Purple blotch in humid spells."],
        "harvest": ["Lift when about half the tops have fallen, then cure in shade with airflow before storage."],
    },
    "chickpea": {
        "season": "Rabi (October-November sowing)",
        "tags": ['pod borer', 'fusarium wilt', 'residual moisture', 'dryland'],
        "display": "Chickpea (gram)", "family": "Pulse legume",
        "summary": "A dryland crop: over-watering brings wilt, not yield.",
        "water": ["Do not over-irrigate. Chickpea is a dryland crop and wet soil brings wilt and root rot.",
                  "One irrigation at pod formation is usually enough where the crop is grown on residual moisture."],
        "nutrition": ["It fixes nitrogen; inoculate and keep the nitrogen dose small."],
        "soil": ["Well-drained soil. It suffers badly on heavy soil that holds water."],
        "problems": ["Pod borer is the main loss; use pheromone traps and act on the count.",
                     "Fusarium wilt - rotate and use resistant varieties rather than treating."],
        "harvest": ["Harvest when plants dry and pods rattle."],
    },
    "mustard": {
        "season": "Rabi (October sowing)",
        "tags": ['aphid', 'white rust', 'sulphur', 'shattering', 'salt tolerant'],
        "display": "Mustard", "family": "Oilseed",
        "summary": "Aphid at pod fill is the usual cause of loss; scout from flowering.",
        "water": ["Flowering and pod filling are the two stages worth protecting; it needs little water otherwise."],
        "nutrition": ["Sulphur matters for oil content and is often deficient."],
        "soil": ["Tolerates a range of soils; it is moderately salt tolerant, which suits saline patches."],
        "problems": ["Check for aphid from flowering onward; a heavy infestation at pod fill is the usual cause of loss.",
                     "White rust in humid spells."],
        "harvest": ["Harvest when pods turn yellow but before they shatter; cut in the cool of the morning."],
    },
    "banana": {
        "season": "Perennial; planted June-July or February-March",
        "tags": ['panama wilt', 'sigatoka', 'bunch', 'propping', 'potassium'],
        "display": "Banana", "family": "Perennial fruit",
        "summary": "Shallow roots and a large leaf area: it needs water almost continuously.",
        "water": ["Banana needs water almost continuously - shallow roots and a large leaf area mean it cannot ride out a dry spell.",
                  "Drip is strongly preferred; flooding wastes water and spreads disease."],
        "nutrition": ["A heavy potassium feeder. Split doses through the season."],
        "soil": ["Deep, well-drained loam with high organic matter. Waterlogging kills the mat."],
        "problems": ["Panama wilt and sigatoka; remove and destroy affected material rather than spraying around it.",
                     "Prop the bunch: a wind-thrown plant at bunch stage is a total loss for that plant."],
        "harvest": ["Harvest at three-quarter fullness for distant markets."],
    },
    "guar": {
        "season": "Kharif (June-July sowing), mostly rainfed",
        "tags": ['bacterial blight', 'jassid', 'gum', 'rainfed', 'root rot'],
        "display": "Guar (cluster bean)", "family": "Pulse legume",
        "summary": "A hardy rainfed legume: it fails from too much water far more often than too little.",
        "water": ["Grown rainfed in most of Gujarat and Rajasthan. One irrigation at flowering is usually the most it needs.",
                  "The first sign of trouble is wilting in a wet field, not a dry one - that is root rot, and irrigating again finishes the crop."],
        "nutrition": ["A legume - inoculate the seed and keep nitrogen minimal."],
        "soil": ["Sandy loam suits it. It tolerates heat and moderate salinity better than most pulses."],
        "problems": ["Bacterial blight in wet spells; use clean seed and avoid overhead irrigation.",
                     "Jassids in dry heat."],
        "harvest": ["For gum, harvest when pods dry on the plant; for vegetable use, pick tender."],
    },
    "coriander": {
        "season": "Rabi (October-November sowing)",
        "tags": ['powdery mildew', 'aphid', 'wilt', 'leaf', 'seed spice', 'aroma'],
        "display": "Coriander", "family": "Seed spice / leafy herb",
        "summary": "Grown for leaf or for seed, and the two want different water.",
        "water": ["Seed colour and aroma are what the buyer grades on, and both are lost if the crop is wet at seed set."],
        "nutrition": ["A light feeder. Excess nitrogen gives soft growth that lodges and invites disease."],
        "soil": ["Well-drained loam. It dislikes both waterlogging and heavy salinity."],
        "problems": ["Powdery mildew in cool dry weather and aphid at flowering.",
                     "Wilt on heavy soils that hold water."],
        "harvest": ["Cut the seed crop when the fruit turns brown but before it shatters; dry in shade to keep the aroma."],
    },
    "ajwain": {
        "season": "Rabi (October-November sowing)",
        "tags": ['powdery mildew', 'aphid', 'umbel', 'seed spice', 'drought hardy'],
        "display": "Ajwain (carom)", "family": "Seed spice",
        "summary": "A hardy rabi spice that needs little water and hates a wet seed set.",
        "water": ["It needs little water: two or three light irrigations usually carry the whole crop."],
        "nutrition": ["A light feeder. It finishes on a small dose, and phosphorus at sowing matters more than nitrogen."],
        "soil": ["Well-drained light to medium soil; it tolerates moderate salinity."],
        "problems": ["Powdery mildew and aphid at flowering are the main losses."],
        "harvest": ["Harvest when the umbels turn brown, and thresh gently to avoid breaking the seed."],
    },
    "white peas": {
        "season": "Rabi (October-November sowing)",
        "tags": ['powdery mildew', 'pod borer', 'pod fill', 'shattering'],
        "display": "White peas", "family": "Pulse legume",
        "summary": "A cool-season pulse: sow on time, and keep the pod-fill stage watered.",
        "water": ["Flowering and pod filling need water; the rest of the season needs very little."],
        "nutrition": ["A legume - inoculate the seed; a small starter dose of phosphorus helps early growth."],
        "soil": ["Well-drained loam, near neutral pH. Poor drainage brings root rot."],
        "problems": ["Powdery mildew late in the season, and pod borer at pod fill.",
                     "Sowing late pushes pod fill into heat, which shrivels the grain."],
        "harvest": ["Harvest when pods are dry and firm; over-dry pods shatter during threshing."],
    },
}

PRACTICE_DOCS: List[Dict[str, Any]] = [
    {
        "id": "practice.irrigation-scheduling", "file": "irrigation-scheduling.md",
        "title": "Irrigation scheduling",
        "summary": "When and how much to irrigate: depletion triggers, critical stages, method efficiency and leaching on saline soil.",
        "tags": ["irrigation", "water", "scheduling", "salinity", "fao56", "depletion"],
        "sections": [
            ("When to irrigate", [
                "Irrigate when the readily available water in the root zone is used up, not on a fixed weekly calendar.",
                "Under FAO-56 the trigger is the depletion fraction p for that crop and stage. Sandy soils hold less water and need smaller, more frequent irrigations; clay soils hold more and need fewer, larger ones.",
                "Check moisture at root depth. The top 5 cm dries misleadingly fast and tells you almost nothing."]),
            ("Critical stages", [
                "Water stress costs most at flowering, pod or grain filling, and tuber bulking. Stress there cannot be made up by watering more later.",
                "Vegetative growth tolerates mild stress far better, and mild early stress can even deepen rooting."]),
            ("How much", [
                "Apply enough to refill the root zone, not the whole profile. Water below the deepest roots is lost, and it carries dissolved nitrogen down with it."]),
            ("Method efficiency", [
                "Surface flooding typically delivers 55-60 percent of applied water to the crop, sprinklers 70-80 percent, and drip 85-95 percent.",
                "Wind above 15 km/h makes sprinkler distribution badly uneven; half the water can land outside the field."]),
            ("Salinity and leaching", [
                "On saline soil apply a leaching fraction: a little extra water beyond the crop need, to push salt below the root zone.",
                "Never let a saline soil dry out fully between irrigations. As water leaves, the remaining salt concentrates and the crop feels it as drought."]),
            ("When not to irrigate", [
                "Do not irrigate when heavy rain is expected within a day; the crop drowns and you pay for the water twice.",
                "Do not irrigate a mature crop that is drying down for harvest: it delays ripening and invites grain mould.",
                "Do not irrigate frozen ground - water ponds and ices instead of infiltrating."]),
        ],
    },
    {
        "id": "practice.pesticide-safety", "file": "pesticide-safety.md",
        "title": "Pesticide safety and spray practice",
        "summary": "Pre-harvest and re-entry intervals, pollinator protection, resistance management, and the conditions a spray needs to work.",
        "tags": ["pesticide", "spray", "safety", "residue", "phi", "rei", "bees", "resistance"],
        "sections": [
            ("Pre-harvest interval", [
                "The pre-harvest interval is the minimum number of days between the last spray and harvest. It is printed on every label and enforced through residue limits.",
                "Harvesting inside it leaves residue above the legal limit: the produce can be rejected at the mandi and is not safe to eat. Nothing washes it off afterwards.",
                "When the label interval is unknown, assume a conservative seven days rather than none."]),
            ("Re-entry interval", [
                "Nobody should enter a treated field before the re-entry interval has passed. Residue on the foliage is still strong enough to harm a person working in it."]),
            ("Protecting pollinators", [
                "Do not apply an insecticide toxic to bees to a crop in flower. Killing the pollinators removes the fruit set the spray was meant to protect.",
                "Where a spray is unavoidable, apply it in the evening after foraging has stopped."]),
            ("Resistance", [
                "Rotate between chemical groups. Repeating the same mode of action selects for a resistant population and the product stops working on that farm permanently."]),
            ("Spray conditions", [
                "Spray in wind between 3 and 15 km/h. Below that, surface inversions carry fine droplets away; above it, the spray drifts onto a neighbour's field.",
                "Spray below 30 degrees Celsius. Above that, fine droplets evaporate before they land.",
                "Allow at least four rain-free hours after application so the product is rainfast.",
                "Cover the underside of leaves: most sucking pests and fungal spores are there, not on top."]),
            ("Personal safety", [
                "Wear gloves, goggles and a mask, and stand so the wind carries the spray away from you.",
                "Wash with soap and change clothes immediately afterwards.",
                "Never wash a sprayer or dump leftover mix near a well, canal or pond."]),
        ],
    },
    {
        "id": "practice.fertilizer-use", "file": "fertilizer-use.md",
        "title": "Fertilizer use",
        "summary": "Splitting nitrogen, placement, timing around rain and irrigation, and reading a soil test.",
        "tags": ["fertilizer", "nitrogen", "urea", "npk", "soil test", "placement"],
        "sections": [
            ("Split the dose", [
                "Split nitrogen into two or three applications across the season. One large dose is largely lost to leaching and to the air, and it pushes soft growth that pests find first."]),
            ("Placement", [
                "Band fertilizer beside the row, about 5 cm from the plant, not against the stem. Salt in contact with seed or stem burns roots and thins the stand."]),
            ("Timing with water", [
                "Apply to moist soil and then irrigate lightly to move the nutrient into the root zone.",
                "Do not apply before heavy rain. Nitrate moves below the roots and reaches groundwater.",
                "Do not broadcast urea on a dry hot surface: up to a third can be lost to the air as ammonia within days.",
                "Do not apply to waterlogged or frozen soil. None of it gets in and it runs off with the first water."]),
            ("Reading a soil test", [
                "A lab test of nitrogen, phosphorus and potassium is the basis of a dose. Sensor conductivity readings estimate salt, not nutrients, and must not be used to set an NPK dose.",
                "Record product, quantity and date. Next season's dose depends on this season's record."]),
            ("Organic matter", [
                "Farmyard manure and compost improve water holding and structure, which is worth more on light soil than any single nutrient dose.",
                "Do not burn crop residue: it destroys the organic matter and nitrogen the next crop needs."]),
        ],
    },
    {
        "id": "practice.soil-salinity", "file": "soil-salinity.md",
        "title": "Salinity and sodic soil",
        "summary": "Reading EC and pH, what salt does to a crop, leaching, gypsum, and which crops tolerate it.",
        "tags": ["salinity", "ec", "sodic", "ph", "gypsum", "leaching", "reclamation"],
        "sections": [
            ("What the readings mean", [
                "Electrical conductivity measures salt in the soil solution. Above a crop's threshold, every further unit costs a predictable percentage of yield (the Maas-Hoffman relationship).",
                "pH above about 8.5 with high sodium indicates a sodic soil, where the problem is structure rather than salt concentration."]),
            ("What salt does", [
                "Salt makes water harder for roots to take up, so a salty field shows drought symptoms while the soil is still moist.",
                "The damage is worst at germination and early growth."]),
            ("Managing salinity", [
                "Apply a leaching fraction with each irrigation to push salt below the root zone, and make sure the field drains.",
                "Keep the soil moist: salt concentrates as water leaves.",
                "Irrigate more often with smaller amounts rather than rarely with large ones."]),
            ("Sodic soil", [
                "Gypsum supplies calcium that displaces sodium, after which the sodium must be leached out. Gypsum without drainage achieves nothing.",
                "Organic matter speeds the recovery."]),
            ("Crop choice", [
                "Where salinity cannot be fixed quickly, choose a tolerant crop: barley, cotton and mustard tolerate more salt than rice, beans or most vegetables."]),
        ],
    },
    {
        "id": "practice.sowing-and-seedbed", "file": "sowing-and-seedbed.md",
        "title": "Seedbed preparation and sowing",
        "summary": "Working soil at the right moisture, sowing depth and spacing, seed treatment, and why the sowing date matters.",
        "tags": ["sowing", "seedbed", "tillage", "spacing", "seed treatment", "germination"],
        "sections": [
            ("Working the soil", [
                "Work soil at the right moisture: it should crumble in the hand, not smear. Tilling wet soil compacts it into clods that no later operation fixes, and black cotton soil is especially unforgiving.",
                "Keep tillage shallow where possible. Deep repeated tillage burns organic matter and forms a hard pan.",
                "Do not work soil to dust either: the first rain seals the surface and seedlings cannot emerge."]),
            ("Seed", [
                "Use certified seed and check the germination percentage before deciding seed rate.",
                "Treat seed against soil-borne disease, and inoculate legume seed with rhizobium.",
                "Do not save seed from a hybrid crop: the next generation does not perform like the parent."]),
            ("Sowing", [
                "Sow at the depth the crop needs. Too deep and the seedling exhausts itself before reaching light.",
                "Keep row spacing right: crowding costs more yield than a slightly thin stand.",
                "Sow into adequate moisture, ideally with rain or irrigation to follow. Sowing dry and hoping is how a stand is lost to one light shower."]),
            ("Sowing date", [
                "The sowing date fixes the whole season's calendar. Late sowing pushes grain filling into heat, and every week of delay costs yield."]),
        ],
    },
    {
        "id": "practice.harvest-and-storage", "file": "harvest-and-storage.md",
        "title": "Harvest and storage",
        "summary": "Judging maturity, harvesting dry, safe storage moisture, and avoiding aflatoxin.",
        "tags": ["harvest", "storage", "moisture", "aflatoxin", "grading", "post-harvest"],
        "sections": [
            ("Judging maturity", [
                "Use the crop's own indicators - grain moisture, pod colour, tuber skin set - rather than the calendar alone.",
                "Delay past maturity and grain shatters, pods split and quality falls every day."]),
            ("Harvesting", [
                "Harvest in a dry spell and line up labour, machinery and transport a day ahead. A harvest that stops half way loses grade.",
                "Keep produce off bare ground and out of the sun after cutting."]),
            ("Drying and storage", [
                "Dry to safe storage moisture before bagging. Produce stored damp heats, moulds and can develop aflatoxin, which makes the lot unsafe and unsellable.",
                "Groundnut and maize are the crops most at risk of aflatoxin; both must be dried promptly and stored ventilated."]),
            ("Grading", [
                "Clean and grade before sale. A grade step usually pays more than it costs, and ungraded produce sets the lowest price of the day in a glut."]),
        ],
    },
    {
        "id": "practice.weather-risk", "file": "weather-risk.md",
        "title": "Heat, frost and storm protection",
        "summary": "Protecting a crop and the people working in it from heat, frost, hail and strong wind.",
        "tags": ["heat", "frost", "storm", "wind", "hail", "safety", "imd"],
        "sections": [
            ("Heat", [
                "Above about 40 degrees Celsius, field work is a safety question, not a preference: start at first light, stop by 11, and drink water every half hour.",
                "Flowering in extreme heat causes poor set in most crops; a light irrigation before a heat spell cools the canopy."]),
            ("Frost", [
                "Ground frost becomes likely when the screen-level minimum approaches 2 degrees Celsius, because the ground runs colder than the air at 2 metres.",
                "A light evening irrigation, or smoke on the windward edge, raises canopy temperature by a degree or two and can be enough.",
                "Young seedlings and flowering crops do not recover from frost damage; mature crops often do."]),
            ("Storm and hail", [
                "Before a forecast storm: harvest what is ready, secure structures, open drains and postpone spraying.",
                "After heavy rain, drain standing water quickly. Roots suffocate within about a day of waterlogging."]),
            ("Wind", [
                "Spraying stops at 15 km/h, not at gale force - see the pesticide safety page. Above that the spray drifts off target.",
                "Above about 39 km/h (IMD strong wind) overhead work, ladders and sprayer booms are unsafe. Above 62 km/h stay out of the field.",
                "Prop or stake tall crops before the season's windy period, not after the first loss."]),
        ],
    },
]


# ── rendering ───────────────────────────────────────────────────────────────

def _agent_facts(crop: str) -> Dict[str, Any]:
    """Facts pulled from the agents that already hold them."""
    facts: Dict[str, Any] = {}
    try:
        from AI_Backend.agents.crop_planning_growth.soil_health.config import CROP_CONFIG as SOIL
        entry = SOIL.get(crop)
        if entry:
            facts["soil"] = entry
    except ImportError:
        pass
    try:
        from AI_Backend.agents.crop_planning_growth.irrigation_planner.config import (
            CROP_CONFIG as IRRIGATION,
        )
        entry = IRRIGATION.get(crop)
        if entry:
            facts["irrigation"] = entry
    except ImportError:
        pass
    try:
        from AI_Backend.agents.farm_operations_automation.task_scheduler.playbook import (
            CROP_PLAYBOOK,
        )
        entry = CROP_PLAYBOOK.get(crop)
        if entry:
            facts["playbook"] = entry
    except ImportError:
        pass
    return facts


def _facts_section(facts: Dict[str, Any]) -> List[str]:
    """The numbers, rendered as a table. Generated, never typed by hand."""
    soil = facts.get("soil") or {}
    irrigation = facts.get("irrigation") or {}
    ranges = soil.get("optimal_ranges") or {}
    rows: List[str] = []
    footnotes: List[str] = []

    def row(label: str, value: Any) -> None:
        if value is None or value == "" or value == [] or value == {}:
            return
        rows.append(f"| {label} | {value} |")

    ph = ranges.get("ph") or {}
    if ph.get("min") is not None and ph.get("max") is not None:
        row("Soil pH", f"{ph['min']} - {ph['max']}")

    # Two different measurements of salt, and confusing them is a real field
    # error. The comfortable range is what a farmer's own meter reads; the
    # tolerance threshold below is ECe from a saturated paste extract in a
    # laboratory, which reads lower than a 1:2 soil-water sample from the same
    # field. They are not comparable numbers.
    ec = ranges.get("ec") or {}
    if ec.get("min") is not None and ec.get("max") is not None:
        row("Comfortable soil EC (dS/m)", f"{ec['min']} - {ec['max']}")

    temp = ranges.get("temperature") or {}
    if temp.get("min") is not None and temp.get("max") is not None:
        row("Optimal soil temperature (C)", f"{temp['min']} - {temp['max']}")

    salinity = soil.get("salinity") or irrigation.get("salinity") or {}
    threshold, slope = salinity.get("threshold"), salinity.get("slope")
    if threshold is not None:
        # Guarded: a config without a slope must publish the threshold alone
        # rather than the words "falls None% per dS/m".
        text = f"{threshold} dS/m (ECe)"
        if slope is not None:
            text += f", then about {slope}% of yield lost per further dS/m"
        row("Salt tolerance threshold", text)
        footnotes.append(
            "Salt tolerance is ECe, measured on a saturated paste extract in a "
            "laboratory (FAO-29, Maas-Hoffman). A field meter reading a 1:2 "
            "soil-water sample gives a different, lower number - the two must "
            "not be compared directly.")

    row("Nitrogen fixing legume", "yes" if soil.get("legume") else None)
    row("Root depth (m)", irrigation.get("root_depth_m"))

    depletion = irrigation.get("p")
    if depletion is not None:
        row("Depletion fraction p", depletion)
        footnotes.append(
            f"The depletion fraction p is the share of the soil's available water "
            f"this crop can use before it starts to suffer. At p = {depletion}, "
            f"irrigate once about {int(float(depletion) * 100)} percent of the "
            "available water in the root zone has been used.")

    row("Season length (days)", irrigation.get("season_days"))
    row("Water management", irrigation.get("water_management"))
    stages = irrigation.get("critical_stages")
    if stages:
        row("Critical stages", ", ".join(stages))
    preferred = irrigation.get("preferred_methods")
    if preferred:
        row("Preferred irrigation", ", ".join(preferred))
    discouraged = irrigation.get("discouraged_methods")
    if discouraged:
        row("Discouraged irrigation", ", ".join(discouraged))
    row("Dries down before harvest",
        "yes" if irrigation.get("dry_down_at_maturity") else None)

    if not rows:
        return []
    block = (["## Field facts", "",
              "Generated from the agent configuration, so these match exactly what "
              "FarmXpert computes with.", "",
              "| Item | Value |", "| --- | --- |"] + rows + [""])
    if footnotes:
        block += [f"- {note}" for note in footnotes] + [""]
    return block


def _key(text: str) -> frozenset:
    """The meaningful words of a sentence, for comparing two pieces of advice."""
    import re
    return frozenset(w for w in re.findall(r"[a-z]{4,}", text.lower())
                     if w not in _COMMON)


_COMMON = frozenset({"that", "this", "with", "from", "into", "have", "been", "will",
                     "your", "when", "what", "which", "they", "them", "than", "then",
                     "does", "over", "under", "after", "before", "because", "about"})


def _already_covered(candidate: str, existing: List[frozenset],
                     threshold: float = 0.6) -> bool:
    """Is this sentence's content already carried by an agent rule?

    Containment, not Jaccard: the question is how much of THIS sentence is
    already said elsewhere, regardless of how much longer the other sentence
    is. A symmetric measure scores a short rule against a long sentence as
    barely similar even when the rule says the whole thing - which is how
    "inoculate the seed" survived twice on the same page.
    """
    key = _key(candidate)
    if not key:
        return False
    for other in existing:
        if other and len(key & other) / len(key) >= threshold:
            return True
    return False


def _crop_markdown(notes: Dict[str, Any], facts: Dict[str, Any]) -> str:
    """One crop page: generated facts, curated prose, and the live agent rules.

    Where the prose and an agent rule say the same thing, the AGENT RULE wins
    and the prose bullet is dropped. That direction matters: the rules are the
    operational source of truth, so if one is edited the page must show the
    new wording. Preferring the prose would let a stale sentence suppress the
    very change this file exists to propagate.
    """
    lines: List[str] = [f"# {notes['display']}", "",
                        f"{notes['summary']}", "",
                        f"Type: {notes['family']}. "
                        f"Season: {notes.get('season', 'not stated')}.", ""]
    lines += _facts_section(facts)

    # Everything the agents themselves say about this crop, which the prose
    # must not repeat.
    playbook = facts.get("playbook") or {}
    soil_advice = (facts.get("soil") or {}).get("crop_advice") or []
    authoritative = [item for rules in playbook.values()
                     for item in list(rules.get("do", [])) + list(rules.get("do_not", []))]
    authoritative += list(soil_advice)
    authoritative_keys = [_key(item) for item in authoritative]

    for heading, key in (("Water", "water"), ("Nutrition", "nutrition"),
                         ("Soil", "soil"), ("Problems to watch", "problems"),
                         ("Harvest", "harvest")):
        items = [item for item in (notes.get(key) or [])
                 if not _already_covered(item, authoritative_keys)]
        if not items:
            continue
        lines += [f"## {heading}", ""] + [f"- {item}" for item in items] + [""]

    if playbook:
        section: List[str] = []
        for category, rules in sorted(playbook.items()):
            entries = [f"- Do: {item}" for item in rules.get("do", [])]
            entries += [f"- Do not: {item}" for item in rules.get("do_not", [])]
            if entries:
                section += [f"### {category.replace('_', ' ').capitalize()}", ""]                     + entries + [""]
        if section:
            lines += ["## Do and do not", "",
                      "The rules the task scheduler attaches to this crop's jobs.",
                      ""] + section

    if soil_advice:
        lines += ["## Soil notes", ""] + [f"- {item}" for item in soil_advice] + [""]

    return "\n".join(lines).rstrip() + "\n"


def _practice_markdown(doc: Dict[str, Any]) -> str:
    lines = [f"# {doc['title']}", "", doc["summary"], ""]
    for heading, items in doc["sections"]:
        lines += [f"## {heading}", ""] + [f"- {item}" for item in items] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _headings(markdown: str) -> List[str]:
    """Section titles. The map carries these because they are what a question
    actually matches against: "Pre-harvest interval" is a far better signal
    than the same words scattered through a summary."""
    return [line.lstrip("# ").strip()
            for line in markdown.splitlines() if line.startswith("##")]


def build(bundle_dir: pathlib.Path = BUNDLE_DIR) -> Dict[str, Any]:
    """Write the bundle and its index. Returns a short report."""
    crops_dir = bundle_dir / "crops"
    practices_dir = bundle_dir / "practices"
    crops_dir.mkdir(parents=True, exist_ok=True)
    practices_dir.mkdir(parents=True, exist_ok=True)

    documents: List[Dict[str, Any]] = []
    missing_facts: List[str] = []

    for crop, notes in sorted(CROP_NOTES.items()):
        facts = _agent_facts(crop)
        if not facts:
            missing_facts.append(crop)
        filename = f"{crop.replace(' ', '-')}.md"
        markdown = _crop_markdown(notes, facts)
        (crops_dir / filename).write_text(markdown, encoding="utf-8")
        # Tags are what retrieval weighs most heavily, so they must
        # DISTINGUISH this crop, not describe every crop. The section names
        # used to be added here, which gave all 19 pages the same four tags
        # and let an unrelated crop outrank the right one.
        tags = ["crop"] + list(notes.get("tags", []))
        tags += [word.lower() for word in notes["family"].replace("/", " ").split()
                 if len(word) > 3]
        if (facts.get("soil") or {}).get("legume"):
            tags.append("legume")
        season = (notes.get("season") or "").lower()
        tags += [term for term in ("kharif", "rabi", "summer", "perennial")
                 if term in season]
        documents.append({
            "id": f"crop.{crop.replace(' ', '-')}",
            "title": notes["display"],
            "summary": notes["summary"],
            "path": f"crops/{filename}",
            "tags": sorted(set(tags)),
            "crops": [crop],
            "headings": _headings(markdown),
            "authority": "farmxpert-agronomy",
            "updated": date.today().isoformat(),
        })

    for doc in PRACTICE_DOCS:
        markdown = _practice_markdown(doc)
        (practices_dir / doc["file"]).write_text(markdown, encoding="utf-8")
        documents.append({
            "id": doc["id"], "title": doc["title"], "summary": doc["summary"],
            "path": f"practices/{doc['file']}", "tags": doc["tags"], "crops": [],
            "headings": _headings(markdown),
            "authority": "farmxpert-agronomy", "updated": date.today().isoformat(),
        })

    written = {(bundle_dir / doc["path"]).resolve() for doc in documents}
    removed = []
    for stale in sorted(bundle_dir.rglob("*.md")):
        if stale.resolve() not in written:
            stale.unlink()
            removed.append(stale.name)

    index = {
        "format": "okf/1.0",
        "bundle": "farmxpert-agronomy",
        "updated": date.today().isoformat(),
        "description": ("Curated agronomy knowledge for FarmXpert. Crop documents are "
                        "generated from the agents' own configuration plus curated "
                        "guidance; practice documents are curated. Regenerate with "
                        "python -m AI_Backend.knowledge.build_okf"),
        "documents": sorted(documents, key=lambda d: d["id"]),
    }
    (bundle_dir / "okf.index.json").write_text(json.dumps(index, indent=2),
                                               encoding="utf-8")
    return {"documents": len(documents),
            "removed_stale": removed,
            "crops": len(CROP_NOTES),
            "practices": len(PRACTICE_DOCS),
            "crops_without_agent_facts": missing_facts,
            "agent_crops_without_a_document": undocumented_agent_crops(),
            "directory": str(bundle_dir)}


def undocumented_agent_crops() -> List[str]:
    """Crops an agent can name that this handbook says nothing about.

    The crop predictor can recommend guar; with no guar page, a farmer asking
    about the crop the model just recommended gets nothing. Better to know at
    build time than from the farmer.
    """
    import importlib

    known: set = set()
    for module, attribute in (
            ("AI_Backend.agents.crop_planning_growth.soil_health.config", "CROP_CONFIG"),
            ("AI_Backend.agents.crop_planning_growth.irrigation_planner.config",
             "CROP_CONFIG"),
            ("AI_Backend.agents.farm_operations_automation.task_scheduler.playbook",
             "CROP_PLAYBOOK")):
        try:
            known |= set(getattr(importlib.import_module(module), attribute))
        except (ImportError, AttributeError):
            continue
    return sorted(known - set(CROP_NOTES))


if __name__ == "__main__":
    report = build()
    print(f"OKF bundle written to {report['directory']}")
    print(f"  {report['documents']} documents "
          f"({report['crops']} crops, {report['practices']} practices)")
    if report["crops_without_agent_facts"]:
        print("  no agent config for: "
              + ", ".join(report["crops_without_agent_facts"]))
    if report["removed_stale"]:
        print("  removed stale pages: " + ", ".join(report["removed_stale"]))
    if report["agent_crops_without_a_document"]:
        print("  WARNING - agents know these crops but the handbook does not: "
              + ", ".join(report["agent_crops_without_a_document"]))

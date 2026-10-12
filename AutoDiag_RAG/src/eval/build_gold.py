"""
Builds the gold evaluation set: data/gold/gold_set.jsonl

Each query has:
  - type: dtc_exact | dtc_paraphrase | symptom | warranty | out_of_scope
  - relevance: a rule that says which corpus chunks count as a correct retrieval
  - reference_answer: short ground-truth answer (used by RAGAS in the evaluation step)
  - warranty_details (warranty queries only): vehicle profile for the rules check

Relevance rule keys (all keys present must match):
  dtc_codes       chunk's dtc_code is in the list, OR the chunk text mentions one of the codes
  source_contains chunk's 'source' contains this text (e.g. "nhtsa")
  warranty_of     chunk is a warranty-booklet chunk of this manufacturer
  text_groups     list of groups; EVERY group must have at least one phrase present in the text

The script checks every rule against all 59,504 chunks and prints how many chunks are relevant
for each query, so no query ends up with zero correct answers in the corpus.
"""
import json
import pickle
import re
from pathlib import Path

CHUNKS_FILE = Path("data/processed/bm25_index/chunks.pkl")
OUT_FILE = Path("data/gold/gold_set.jsonl")

# ---------------------------------------------------------------------------------------------
# 1. Exact DTC queries — the code is in the question (keyword search should be strong here)
# ---------------------------------------------------------------------------------------------
DTC_EXACT = [
    ("What does code P0301 mean and what usually causes it?", ["P0301"],
     "P0301 means a misfire was detected in cylinder 1. Common causes are a worn spark plug, a faulty ignition coil, a clogged or leaking fuel injector, or low compression in that cylinder."),
    ("My scanner shows P0300. Is it serious?", ["P0300"],
     "P0300 means random or multiple cylinder misfires were detected. It should be fixed soon because misfires can damage the catalytic converter; causes include spark plugs, coils, vacuum leaks or fuel delivery problems."),
    ("Check engine light shows P0420 — what should I check?", ["P0420"],
     "P0420 means catalyst system efficiency is below threshold on bank 1. Check for exhaust leaks, faulty oxygen sensors, engine misfires, and finally a worn catalytic converter."),
    ("What is DTC P0430?", ["P0430"],
     "P0430 means catalyst system efficiency is below threshold on bank 2, usually from a failing catalytic converter, oxygen sensor fault or exhaust leak."),
    ("Code P0171 came up, what does system too lean mean?", ["P0171"],
     "P0171 means the system is too lean on bank 1: too much air or too little fuel. Typical causes are vacuum leaks, a dirty MAF sensor, a weak fuel pump or clogged injectors."),
    ("Explain trouble code P0172", ["P0172"],
     "P0172 means the system is too rich on bank 1: too much fuel or too little air. Causes include leaking injectors, high fuel pressure, a faulty MAF or oxygen sensor, or a dirty air filter."),
    ("P0128 thermostat code meaning", ["P0128"],
     "P0128 means coolant temperature is below the thermostat regulating temperature, usually because the thermostat is stuck open or the coolant temperature sensor is faulty."),
    ("How do I fix P0442?", ["P0442"],
     "P0442 means a small leak was detected in the evaporative emission (EVAP) system. Check the gas cap seal first, then EVAP hoses, the purge valve and the vent valve."),
    ("What causes P0455?", ["P0455"],
     "P0455 means a large leak was detected in the EVAP system, most often a missing or loose gas cap, a disconnected hose, or a faulty purge or vent valve."),
    ("Car won't start and shows P0335", ["P0335"],
     "P0335 is a crankshaft position sensor A circuit malfunction. Without a crank signal the engine may crank but not start; check the sensor, its wiring and connector."),
    ("What does P0340 indicate?", ["P0340"],
     "P0340 is a camshaft position sensor A circuit malfunction (bank 1), caused by a faulty sensor, damaged wiring or timing problems."),
    ("Meaning of code P0101", ["P0101"],
     "P0101 means the mass air flow (MAF) sensor circuit is out of range or has a performance problem, often from a dirty MAF sensor, air leaks after the sensor, or a clogged air filter."),
    ("Transmission light with code P0700", ["P0700"],
     "P0700 means the transmission control system has a malfunction; the transmission control module has stored its own fault codes that need to be read for the exact cause."),
    ("What is P0401 EGR code?", ["P0401"],
     "P0401 means insufficient exhaust gas recirculation (EGR) flow, usually from carbon-clogged EGR passages, a stuck EGR valve or a faulty EGR sensor."),
]

# ---------------------------------------------------------------------------------------------
# 2. DTC paraphrase queries — same faults, described in words with NO code (semantic search test)
# ---------------------------------------------------------------------------------------------
DTC_PARAPHRASE = [
    ("Engine is misfiring in cylinder number one", ["P0301"],
     "A misfire in cylinder 1 corresponds to DTC P0301; check the spark plug, ignition coil and injector of cylinder 1."),
    ("Random misfires happening across several cylinders", ["P0300"],
     "Random or multiple cylinder misfires correspond to DTC P0300; causes include ignition, fuel delivery or vacuum leak problems."),
    ("Catalytic converter efficiency is too low on bank 1", ["P0420"],
     "Low catalyst efficiency on bank 1 corresponds to DTC P0420; usually a worn catalytic converter, oxygen sensor fault or exhaust leak."),
    ("Engine running lean on bank 1, too much air and not enough fuel", ["P0171"],
     "A lean condition on bank 1 corresponds to DTC P0171; causes include vacuum leaks, a dirty MAF sensor or low fuel pressure."),
    ("Engine running too rich on bank one", ["P0172"],
     "A rich condition on bank 1 corresponds to DTC P0172; causes include leaking injectors, high fuel pressure or a faulty MAF/oxygen sensor."),
    ("Coolant temperature stays below the thermostat regulating temperature", ["P0128"],
     "Coolant staying below thermostat temperature corresponds to DTC P0128, usually a thermostat stuck open."),
    ("Small leak detected in the evaporative emission system", ["P0442"],
     "A small EVAP leak corresponds to DTC P0442; check the gas cap and EVAP hoses."),
    ("Large leak in the fuel vapour EVAP system, gas cap may be missing", ["P0455", "P0457"],
     "A large EVAP leak or loose/missing fuel cap corresponds to DTC P0455 or P0457."),
    ("Crankshaft position sensor circuit problem, engine cranks but does not start", ["P0335", "P0336", "P0337", "P0338", "P0339"],
     "Crankshaft position sensor faults correspond to DTCs P0335–P0339; the engine may crank but not start."),
    ("Mass air flow sensor reading is out of range", ["P0100", "P0101", "P0102", "P0103", "P0104"],
     "Mass air flow sensor faults correspond to DTCs P0100–P0104, often caused by a dirty or failed MAF sensor."),
    ("Engine idle speed is higher than expected", ["P0507", "P0505"],
     "Higher than expected idle speed corresponds to DTC P0507 (idle air control system), often from a vacuum leak or dirty throttle body."),
    ("Not enough exhaust gas recirculation flow detected", ["P0401"],
     "Insufficient EGR flow corresponds to DTC P0401, usually clogged EGR passages or a stuck EGR valve."),
]

# ---------------------------------------------------------------------------------------------
# 3. Symptom queries — answered by NHTSA owner complaints
# ---------------------------------------------------------------------------------------------
SYMPTOM = [
    ("My car makes a rattling noise when accelerating",
     [["rattl"], ["accelerat"]],
     "Owners report rattling noises under acceleration; reported causes include engine internal problems such as bearings, loose heat shields or exhaust components, and drivetrain issues."),
    ("Steering wheel feels stiff and hard to turn",
     [["steer"], ["stiff", "hard to turn", "difficult to turn", "heavy"]],
     "Stiff or heavy steering is commonly reported with power steering failures, including electric power steering assist loss, and is a safety concern."),
    ("Brake pedal goes all the way to the floor",
     [["brake"], ["floor"]],
     "A brake pedal sinking to the floor indicates loss of brake pressure, such as a brake fluid leak or master cylinder failure, and the vehicle should not be driven."),
    ("Car shakes and vibrates at highway speed",
     [["vibrat", "shak"], ["highway", "mph", "high speed"]],
     "Vibration at highway speed is commonly linked to wheel balance, tire, driveshaft/axle or suspension problems."),
    ("Transmission jerks and hesitates when shifting gears",
     [["transmission"], ["jerk", "hesitat", "slip", "lurch"]],
     "Owners report harsh, jerky or hesitant shifting and slipping, linked to transmission or transmission control problems."),
    ("Engine stalls while driving",
     [["stall"], ["driving", "while driv", "highway"]],
     "Engine stalling while driving is reported with fuel delivery, electrical and engine control failures and is a serious safety risk."),
    ("Airbag warning light stays on",
     [["air bag", "airbag"], ["light", "warning"]],
     "An illuminated airbag warning light means the supplemental restraint system detected a fault and the airbags may not deploy."),
    ("Check engine light came on and the car lost power",
     [["check engine", "engine light", "malfunction indicator"], ["loss of power", "lost power", "power loss", "reduced power", "limp"]],
     "A check engine light with loss of power often indicates the engine entering reduced power (limp) mode due to engine, turbo, fuel or sensor faults."),
    ("There is a burning smell coming from the engine",
     [["burn"], ["smell", "odor", "odour"]],
     "A burning smell is reported with oil or fluid leaks onto hot exhaust parts, overheating, or electrical faults, and can be a fire risk."),
    ("Car won't start and just makes a clicking sound",
     [["start"], ["click"]],
     "A clicking sound with no start usually points to a weak battery, poor battery connections or a failing starter."),
    ("Sudden unintended acceleration while braking",
     [["unintended", "sudden", "surge", "surging"], ["accelerat"]],
     "Owners report sudden or unintended acceleration events, a serious safety defect investigated by NHTSA."),
    ("Headlights flicker or suddenly go dark",
     [["headlight", "head light", "headlamp"], ["flicker", "dim", "go out", "went out", "turn off", "shut off"]],
     "Headlight flicker or failure is reported with wiring, connector, bulb or lighting control module problems, reducing visibility at night."),
]

# ---------------------------------------------------------------------------------------------
# 4. Warranty queries — answered by manufacturer warranty booklets (+ deterministic rules check)
# ---------------------------------------------------------------------------------------------
WARRANTY = [
    ("Is my Honda powertrain still covered under warranty?", "Honda", [["powertrain"]],
     {"manufacturer": "Honda", "component": "powertrain", "vehicle_age_years": 4, "mileage": 55000},
     "Yes. Honda's powertrain warranty lasts 5 years or 60,000 miles, whichever comes first, so a 4-year-old car with 55,000 miles is still covered."),
    ("How long are Honda seat belts covered?", "Honda", [["seat belt", "seatbelt"]],
     {"manufacturer": "Honda", "component": "seat_belts", "vehicle_age_years": 6, "mileage": 80000},
     "Honda covers seat belts for 15 years or 150,000 miles, so a 6-year-old car with 80,000 miles is covered."),
    ("Does the Hyundai powertrain warranty cover my car at 90,000 miles?", "Hyundai", [["powertrain"]],
     {"manufacturer": "Hyundai", "component": "powertrain", "vehicle_age_years": 7, "mileage": 90000},
     "Yes. Hyundai's powertrain warranty lasts 10 years or 100,000 miles, so a 7-year-old car with 90,000 miles is covered."),
    ("Is the Hyundai basic warranty still valid after 6 years?", "Hyundai", [["limited warranty", "new vehicle", "basic"]],
     {"manufacturer": "Hyundai", "component": "basic", "vehicle_age_years": 6, "mileage": 50000},
     "No. Hyundai's basic (new vehicle limited) warranty lasts 5 years or 60,000 miles, so at 6 years it has expired by time."),
    ("Is the Toyota hybrid battery covered under warranty?", "Toyota", [["hybrid"], ["battery"]],
     {"manufacturer": "Toyota", "component": "hybrid_battery", "vehicle_age_years": 9, "mileage": 120000},
     "Yes. Toyota covers the hybrid battery for 10 years or 150,000 miles, so a 9-year-old car with 120,000 miles is covered."),
    ("Does Toyota cover rust and corrosion?", "Toyota", [["corrosion", "perforation", "rust"]],
     {"manufacturer": "Toyota", "component": "corrosion", "vehicle_age_years": 4, "mileage": 70000},
     "Toyota covers corrosion perforation for 5 years with unlimited miles, so a 4-year-old car is covered regardless of mileage."),
    ("Would a Ford transmission repair be covered at 45,000 miles?", "Ford", [["powertrain", "transmission"]],
     {"manufacturer": "Ford", "component": "powertrain", "vehicle_age_years": 3, "mileage": 45000},
     "Yes. The transmission falls under Ford's powertrain warranty of 5 years or 60,000 miles, so 3 years and 45,000 miles is covered."),
    ("Is my Ford bumper-to-bumper warranty still active at 40,000 miles?", "Ford", [["bumper", "new vehicle limited warranty", "basic"]],
     {"manufacturer": "Ford", "component": "basic", "vehicle_age_years": 2, "mileage": 40000},
     "No. Ford's bumper-to-bumper (basic) coverage lasts 3 years or 36,000 miles, so it has expired at 40,000 miles."),
    ("Is the Nissan powertrain covered after 70,000 miles?", "Nissan", [["powertrain"]],
     {"manufacturer": "Nissan", "component": "powertrain", "vehicle_age_years": 4, "mileage": 70000},
     "No. Nissan's powertrain warranty lasts 5 years or 60,000 miles, so it has expired at 70,000 miles."),
    ("Does the Kia warranty cover the engine for 10 years?", "Kia", [["powertrain", "engine"]],
     {"manufacturer": "Kia", "component": "powertrain", "vehicle_age_years": 8, "mileage": 85000},
     "Yes. Kia's powertrain warranty lasts 10 years or 100,000 miles, so an 8-year-old car with 85,000 miles is covered."),
]

# ---------------------------------------------------------------------------------------------
# 5. Out-of-scope queries — the confidence gate SHOULD defer these (not used for retrieval metrics)
# ---------------------------------------------------------------------------------------------
OUT_OF_SCOPE = [
    "What is a good recipe for chocolate cake?",
    "Who won the football world cup in 2018?",
    "How do I reset my Wi-Fi router password?",
    "What is the capital of Australia?",
]


def is_relevant(rule: dict, text: str, metadata: dict) -> bool:
    """True if a chunk satisfies the query's relevance rule."""
    if not rule:
        return False
    text_l = (text or "").lower()
    metadata = metadata or {}

    if "dtc_codes" in rule:
        codes = [c.upper() for c in rule["dtc_codes"]]
        meta_code = str(metadata.get("dtc_code") or "").upper()
        if meta_code not in codes and not any(re.search(rf"\b{c.lower()}\b", text_l) for c in codes):
            return False

    if "source_contains" in rule:
        if rule["source_contains"].lower() not in str(metadata.get("source", "")).lower():
            return False

    if "warranty_of" in rule:
        source = str(metadata.get("source", "")).lower()
        is_warranty = metadata.get("doc_type") == "warranty" or source.endswith(".pdf")
        if not is_warranty or str(metadata.get("manufacturer", "")).lower() != rule["warranty_of"].lower():
            return False

    for group in rule.get("text_groups", []):
        if not any(phrase.lower() in text_l for phrase in group):
            return False

    return True


def build_queries() -> list:
    queries = []
    for i, (q, codes, ref) in enumerate(DTC_EXACT, 1):
        queries.append({"id": f"DX{i:02d}", "type": "dtc_exact", "query": q,
                        "relevance": {"dtc_codes": codes}, "reference_answer": ref})
    for i, (q, codes, ref) in enumerate(DTC_PARAPHRASE, 1):
        queries.append({"id": f"DP{i:02d}", "type": "dtc_paraphrase", "query": q,
                        "relevance": {"dtc_codes": codes}, "reference_answer": ref})
    for i, (q, groups, ref) in enumerate(SYMPTOM, 1):
        queries.append({"id": f"SY{i:02d}", "type": "symptom", "query": q,
                        "relevance": {"source_contains": "nhtsa", "text_groups": groups}, "reference_answer": ref})
    for i, (q, mfr, groups, details, ref) in enumerate(WARRANTY, 1):
        queries.append({"id": f"WA{i:02d}", "type": "warranty", "query": q,
                        "relevance": {"warranty_of": mfr, "text_groups": groups},
                        "warranty_details": details, "reference_answer": ref})
    for i, q in enumerate(OUT_OF_SCOPE, 1):
        queries.append({"id": f"OS{i:02d}", "type": "out_of_scope", "query": q,
                        "relevance": None, "reference_answer": None})
    return queries


def main():
    print(f"Loading corpus from {CHUNKS_FILE} ...")
    with open(CHUNKS_FILE, "rb") as f:
        chunks = pickle.load(f)
    print(f"Corpus: {len(chunks):,} chunks\n")

    queries = build_queries()
    problems = 0
    print(f"{'ID':5s} {'TYPE':15s} {'RELEVANT':>9s}  QUERY")
    print("-" * 95)
    for q in queries:
        if q["relevance"] is None:
            q["n_relevant"] = 0
            print(f"{q['id']:5s} {q['type']:15s} {'—':>9s}  {q['query'][:60]}")
            continue
        n = sum(1 for c in chunks if is_relevant(q["relevance"], c["text"], c.get("metadata")))
        q["n_relevant"] = n
        flag = "   <-- NO RELEVANT CHUNKS, fix this query" if n == 0 else ""
        problems += n == 0
        print(f"{q['id']:5s} {q['type']:15s} {n:>9,}  {q['query'][:60]}{flag}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    by_type = {}
    for q in queries:
        by_type[q["type"]] = by_type.get(q["type"], 0) + 1
    print("-" * 95)
    print(f"Saved {len(queries)} queries to {OUT_FILE}  ->  {by_type}")
    print("All queries have relevant chunks." if problems == 0 else f"WARNING: {problems} queries have 0 relevant chunks.")


if __name__ == "__main__":
    main()
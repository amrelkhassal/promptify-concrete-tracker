from app.domain.models import FieldSpec, FieldType


DEFAULT_PROMPT = """You are an expert at extracting structured data from concrete delivery notes. The document may be in any language — identify fields by their position, layout, and semantic meaning, not by matching exact label wording.

EXTRACTION RULES:

1. LANGUAGE
   Detect the document language automatically. Map field labels to their semantic meaning regardless of language or abbreviation used.

2. TIME TABLE
   The document contains a table with multiple time columns recorded in chronological order. Extract each time field strictly by its column position and semantic role, not by label wording alone:
   - "1ère gâchée" / "loading time" / "ΩΡΑ ΦΟΡΤΩΣΗΣ": time of first batch at the plant.
   - Column 1: Arrival on site (Arrivée chantier / arrival / ώρα άφιξης)
   - Column 2: Start of unloading or pumping (Début vidange ou pompage / start unloading)
   - Column 3: End of unloading or pumping (Fin vidange ou pompage / end unloading)
   - Column 4: Departure from site (Départ chantier / site departure / ώρα αναχώρησης εργοταξίου)
   - "Limite d'utilisation" / "use limit" / "όριο χρήσης" → this is a deadline, NOT a site event. Never return this as the departure time.

3. NUMBERS
   Return numeric values as plain numbers using a dot as the decimal separator (e.g. 7.5). Do not include units in numeric fields.

4. DATES
   Always return dates in dd/mm/yyyy format, regardless of how they appear in the document (FR, EN, ISO, GR…). Two-digit years (e.g. 12/05/25) must be expanded to four digits (12/05/2025).

5. TIMES
   Always return times in hh:mm (24-hour) format. If the document uses HH:MM:SS, drop the seconds.

6. BOOLEAN
   Return true only if the document explicitly confirms the field (e.g. pumping), false otherwise.

7. ENUM FIELDS (technical concrete specs)
   Return the value EXACTLY as printed when it matches one of the standardised options (e.g. "C25/30", "XC2", "S3", "Cl 0,40", "CEM II/A-L"). If the document lists several exposure classes, return ONLY the first.

8. TABLES — DO NOT CONFUSE HEADERS WITH VALUES
   Column headers appear ABOVE the data rows. Never return a header label as a field value. Example (Greek):
     | ΕΙΔΟΣ  | ΦΑΙΝΟΜΕΝΟ ΕΙΔΙΚΟ ΒΑΡΟΣ |
     | C16/20 | 2,258 kgs              |
   ✅ "typeBeton": "C16/20"      ❌ "typeBeton": "ΕΙΔΟΣ" / "ΦΑΙΝΟΜΕΝΟ"

9. DELIVERY NUMBER
   The delivery number is mandatory and is a 6–8 digit number near the top of the document. Look first next to a label (BL / Bon de livraison / Delivery Note / DN / αριθμός φορτωτικής); fall back to the highest isolated 6–8 digit number that is not a phone, date, time, quantity, order number, or truck number.

10. MISSING VALUES
    Return null for any field not found or not clearly legible. Do not infer or fabricate values."""


DEFAULT_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="deliveryNumber",
        label="N° bon de livraison",
        description="Delivery note number — 6 to 8 digits, near the top of the document. May appear with or without a label. Mandatory.",
        example="123456",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="typeBeton",
        label="Type de béton",
        description="Concrete type / formula code as printed (e.g. BC2520C24H, C25/30). Locate by position in the concrete specification section, not by label wording alone.",
        example="BC2520C24H",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="designation",
        label="Désignation",
        description="Full technical description of the concrete mix as written. May span multiple lines. If absent, fall back to the typeBeton value.",
        example="Béton de structure C25/30 XC2",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="concreteCode",
        label="Code béton",
        description="Concrete reference code as printed. May be identical to typeBeton.",
        example="BC2520C24H",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="quantity",
        label="Quantité",
        description='Total volume delivered as a plain number with dot decimal separator. If a "Quantity this load" field is present, use it exclusively. Do NOT include the unit.',
        example="7.5",
        type=FieldType.NUMERIC,
    ),
    FieldSpec(
        name="unit",
        label="Unité",
        description="Unit of the delivered volume as printed (e.g. m³, m3).",
        example="m³",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="dateLivraison",
        label="Date de livraison",
        description="Date of the first batch in dd/mm/yyyy. Convert from any source format.",
        example="15/03/2024",
        type=FieldType.DATE,
    ),
    FieldSpec(
        name="heurePremiereGachee",
        label="Heure 1ère gâchée",
        description="Time of the first batch at the plant in hh:mm (24h). Equivalent labels: loading time, 1re gâchée, ΩΡΑ ΦΟΡΤΩΣΗΣ.",
        example="13:45",
        type=FieldType.TIME,
    ),
    FieldSpec(
        name="heureArriveeChantier",
        label="Arrivée chantier",
        description="Time the truck arrived on site in hh:mm (24h). FIRST column of the on-site time table.",
        example="14:10",
        type=FieldType.TIME,
    ),
    FieldSpec(
        name="heureDebutDechargement",
        label="Début vidange / pompage",
        description='Time unloading or pumping STARTED in hh:mm (24h). SECOND column of the time table — labelled "Début vidange ou pompage" / "Start unloading".',
        example="14:15",
        type=FieldType.TIME,
    ),
    FieldSpec(
        name="heureFinDechargement",
        label="Fin vidange / pompage",
        description='Time unloading or pumping ENDED in hh:mm (24h). THIRD column of the time table — labelled "Fin vidange ou pompage" / "End unloading".',
        example="14:40",
        type=FieldType.TIME,
    ),
    FieldSpec(
        name="heureDepartChantier",
        label="Départ chantier",
        description='Time the truck departed from site in hh:mm (24h). FOURTH column of the time table. Do NOT use the "Limite d\'utilisation" / "use limit" column, which is a deadline.',
        example="14:53",
        type=FieldType.TIME,
    ),
    FieldSpec(
        name="pumping",
        label="Pompage",
        description="true if the document explicitly indicates pumping was used, false otherwise.",
        example="true",
        type=FieldType.BOOLEAN,
    ),
    FieldSpec(
        name="additive",
        label="Addition",
        description="Mineral addition used (e.g. fly ash, slag, silica fume). Return null if none.",
        example="Plastiment BV40",
        type=FieldType.STRING,
    ),
    FieldSpec(
        name="adjuvant",
        label="Adjuvant",
        description="Chemical admixture type. Allowed values: Aucun, PRE, SPHRE, AP, AD. Return 'Aucun' when explicitly absent, null when not mentioned.",
        example="PRE",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="carboneWeight",
        label="Poids carbone",
        description="Carbon weight as a plain number with dot decimal separator (kg CO₂). Return null if absent.",
        example="123.8",
        type=FieldType.NUMERIC,
    ),
    FieldSpec(
        name="classeExposition",
        label="Classe d'exposition",
        description="First exposure class only (if multiple are listed, keep ONLY the first). Allowed: X0, XC1–XC4, XD1–XD3, XS1–XS3, XF1–XF4. Return null if absent.",
        example="XC2",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="classeResistance",
        label="Classe de résistance",
        description="Characteristic compressive strength class. Allowed: C8/10 … C100/115, LC8/9 … LC80/88. Return null if absent.",
        example="C25/30",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="classeChlorures",
        label="Classe de chlorures",
        description="Chloride content class. Allowed: Cl 0,10 / Cl 0,20 / Cl 0,40 / Cl 0,65 / Aucun. Normalise to 'Cl X,XX'. Return null if absent.",
        example="Cl 0,40",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="classeConsistance",
        label="Classe de consistance",
        description="Slump (consistency) class. Allowed: S1, S2, S3, S4, S5, SF1, SF2, SF3. Return null if absent.",
        example="S3",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="familleCiment",
        label="Famille de ciment",
        description="Cement family as printed. Allowed values include: CEM I, CEM II/A-L, CEM II/A-LL, CEM II/A-M, CEM II/B, CEM III/A, CEM III/B, CEM IV/A, CEM V/A, H-UKR, CARAT, CEM VI (and other CEM II/III/IV/V variants). Return null if absent.",
        example="CEM II/A-L",
        type=FieldType.ENUM,
    ),
    FieldSpec(
        name="diametreGranulat",
        label="Diamètre de granulat (Dmax)",
        description="Maximum aggregate diameter (Dmax) as printed. Return null if absent.",
        example="22",
        type=FieldType.ENUM,
    ),
]

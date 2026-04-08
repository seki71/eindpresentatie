# Examenvoorbereiding – Case 8 EV Cars & Charging

## Verhaallijn voor 8 minuten

### 1. Begin – probleemstelling
"Mijn onderzoeksvraag is: waar groeit de vraag naar elektrisch rijden sneller dan de publieke laadinfrastructuur?"

### 2. Midden – analyse
- Ik heb de EV-populatiedata opgeschoond op county, postcode en voertuiglocatie.
- Ik heb de laadstationdata gefilterd op **elektrisch**, **publiek toegankelijk** en **beschikbaar / tijdelijk onbeschikbaar**.
- Voor de kaart toon ik EV-vraag geaggregeerd per ZIP-code en laadstations als punten.
- Voor de analyse vergelijk ik per county het aantal EV's met het aantal publieke laadpoorten.
- Als historische data beschikbaar is, bereken ik een echte growth gap.

### 3. Eind – conclusie / advies
- Noem 2 of 3 counties met de hoogste gap score.
- Advies: prioriteer juist die counties voor nieuwe publieke laadlocaties.
- Laat zien dat je dashboard interactieve filters heeft voor BEV-only, top-N en analyseperiode.

## Waarom deze visualisaties?
- **Kaart**: ruimtelijke spreiding van vraag en aanbod.
- **Bar chart**: makkelijk vergelijken van counties met grootste tekort.
- **Scatterplot**: laat verhouding tussen EV-volume en laadpoorten zien.
- **Tabellen**: detailcontrole en transparantie.

## Antwoorden voor de IDS-verdediging

### Waarom datum omzetten?
Omdat strings niet geschikt zijn voor tijdsvergelijkingen. Voor groei over 12 maanden moet ik kunnen rekenen met echte datums.

### Waarom filter je laadstations?
Omdat de case gaat over **publieke EV-infrastructuur**. Private of geplande stations zouden het beeld vertekenen.

### Waarom groupby?
De ruwe EV-dataset heeft veel individuele registraties. Voor analyse op county- of ZIP-niveau moet ik eerst aggregeren.

### Waarom een left join?
Omdat ik counties zonder laadpalen ook wil behouden. Juist die regio's zijn belangrijk voor de gap-analyse.

### Waarom niet alle 150k punten direct op de kaart?
Dat maakt de app traag en onoverzichtelijk. Daarom aggregeer ik EV's eerst per ZIP-code.

### Wat doe je met missende waarden?
- Missende coördinaten: niet op de kaart tonen.
- Missende poorten: als 0 interpreteren na de merge.
- Missende historische waarden: fallback naar current pressure score of vullen met 0 waar dat inhoudelijk klopt.

## Live-coding dingen die je snel moet kunnen

### Top-N slider
De app heeft al:
```python
 top_n = st.slider("Top N counties / ZIP-codes", 5, 20, 10, 5)
```

### Nieuwe kolom toevoegen
```python
county_table["evs_per_station"] = county_table["ev_count_current"] / county_table["station_count"].replace(0, pd.NA)
```

### Sorteren hoog naar laag
```python
county_table = county_table.sort_values("gap_score", ascending=False)
```

### Alleen BEV filter
```python
ev_filtered = ev_raw[ev_raw["Electric Vehicle Type"].str.contains("Battery", case=False, na=False)].copy()
```

### Gemiddelde i.p.v. som in groupby
```python
ev_by_county = ev_df.groupby("County")["Electric Range"].mean().reset_index()
```

## Sterke slotzin
"Mijn dashboard laat niet alleen zien waar de meeste EV's zijn, maar vooral waar de infrastructuur achterblijft op de groei van elektrisch rijden."

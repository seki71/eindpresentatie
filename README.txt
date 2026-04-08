Bestandsstructuur
-----------------
ev_dashboard/
  app.py
  requirements.txt
  data/
    Electric_Vehicle_Population_Data.csv
    Charging_Stations.csv
    EV_Population_Size_History_By_County.csv   (optioneel maar aanbevolen)

Starten
-------
1. Maak een virtuele omgeving.
2. Installeer dependencies:
   pip install -r requirements.txt
3. Maak een map 'data' naast app.py.
4. Zet de CSV-bestanden daarin.
5. Start de app:
   streamlit run app.py

Opmerkingen
-----------
- De app verwacht een EV-bestand met kolommen zoals County, Postal Code en Vehicle Location.
- Het laadstationbestand verwacht AFDC-achtige kolommen zoals fuel_type_code, access_code,
  status_code, zip, latitude, longitude, ev_level2_evse_num, ev_dc_fast_num en open_date.
- Als EV_Population_Size_History_By_County.csv ontbreekt, gebruikt de app een fallback-analyse.

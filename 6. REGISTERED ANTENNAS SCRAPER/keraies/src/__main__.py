import asyncio

from .main import main
from .main_scrape_antennaidsonly import main_scrape_antennaidsonly
from .main_Scrape_specific_missing_AntennaIDS import main_Scrape_specific_missing_AntennaIDS

# epilegeis poio py arxeio tha ekteleseis gia na min ftiaxno neo actor
# to kirio einai to main.py to opoio gia kapoio logo exase 4133 keraies apo tis 24153 gia agnosto logo
# ena lathos itan oti eleipe apo tous dimous o Dimos Abdiron - ok to eftiaksa
# prosoxi exei input.json sto keyvaluestore ---- ayto diabazei kai OXI to arxeio pou exo episinapsei sto root

# Execute the Actor entrypoint.
#asyncio.run(main())
#asyncio.run(main_scrape_antennaidsonly())
asyncio.run(main_Scrape_specific_missing_AntennaIDS())

# Leader reference tables — sources and caveats

Compiled 2026-10-08 in chat from English Wikipedia (via a page-reading tool; every row needs spot verification):

| File | Source page |
|---|---|
| apostles_raw.csv | https://en.wikipedia.org/wiki/Chronology_of_the_Quorum_of_the_Twelve_Apostles_(LDS_Church) |
| first_presidency_raw.csv | https://en.wikipedia.org/wiki/Chronology_of_the_First_Presidency_(LDS_Church) |
| q12_presidents_raw.csv | https://en.wikipedia.org/wiki/President_of_the_Quorum_of_the_Twelve_Apostles_(LDS_Church) |
| presiding_bishopric_raw.csv | https://en.wikipedia.org/wiki/Presiding_Bishop_(LDS_Church) |
| auxiliary_presidents_raw.csv | Relief Society: https://en.wikipedia.org/wiki/List_of_general_presidencies_of_the_Relief_Society ; Young Women: https://en.wikipedia.org/wiki/Young_Women_(organization) ; Primary: https://en.wikipedia.org/wiki/Primary_(LDS_Church) ; Sunday School: https://en.wikipedia.org/wiki/Sunday_School_(LDS_Church) ; Young Men: https://en.wikipedia.org/wiki/Young_Men_(organization) |

Caveats
- Apostle "ordained" dates for Hinckley, Monson, Packer, McConkie, Perry, Faust, Hales, Eyring and everyone after are the dates they were *added to the Quorum* (the page gave no ordination date).
- Auxiliary presidents (except Relief Society) have years only.
- Young Men 1974–1977 gap is as given on the page (program reorganizations).
- Seventies are not listed here; they are captured automatically from talk bylines during import.
- Diacritics are removed from names (e.g., Gerald Causse) to keep CSVs plain ASCII.
- Recent changes (Oct 2025–2026) came from Wikipedia and are the most likely to need correction:
  Oaks President 2025-10-14 with Eyring and Christofferson; Holland President of the Twelve 2025-10-14 to his death 2025-12-27;
  Eyring President of the Twelve from 2025-12-27 with Uchtdorf Acting President from 2026-01-08; Causse ordained 2025-11-06;
  Gilbert ordained 2026-02-12; Waddell Presiding Bishop 2025-11-14; Chibota Primary 2026; Farnes Young Men 2025.
- Claude Code must verify these against churchofjesuschrist.org leader pages and the talk bylines (CP-2.4).

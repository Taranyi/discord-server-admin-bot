# Discord Bot

Igény szerint, helyben futtatott Discord-szerveradminisztrációs eszköz egy MSc
hallgatói közösség számára. Az adminisztrátor elindítja, amikor szüksége van rá,
majd a munka végeztével leállítja. A bot által később létrehozott Discord-erőforrások
offline állapotban is megmaradnak.

A helyes működéshez nem szükséges, hogy folyamatosan fusson. Az adminisztrátor a
bot futása közben és offline állapotában is módosíthatja a Discordot; a következő
indítás utáni szinkronizálás a szerver aktuális állapotát használja, nem olyan
eseményekre támaszkodik, amelyeket a folyamat korábban esetleg látott.

A jelenlegi MVP részei:

- környezeti változókon alapuló konfiguráció;
- minimális, nem privilegizált Gateway intentek;
- szabályozható szerver- vagy globális alkalmazásparancs-szinkronizálás;
- biztonságos helyi naplózás;
- minden parancsra érvényes, központi adminisztrátori jogosultság-ellenőrzés;
- YAML-alapú kurzussablon;
- helyi SQLite kezelt állapot;
- szemeszterek létrehozása és listázása;
- kurzusok létrehozása, listázása, lekérdezése és a Discord állapotát elsődlegesnek
  tekintő szinkronizálása;
- kezelt kurzusok és üres szemeszterek előnézetes törlése;
- nyilvántartott közös csatornák létrehozása és törlése minden kezelt kurzusban;
- privát diagnosztikai `/server status` parancs.

A szerepkörkezelés, archiválás/visszaállítás, tömeges kurzusimport és a teljes
szerverstruktúra kezelése még nincs megvalósítva.

Angol dokumentáció: [README.md](README.md)

## Követelmények

- Python 3.11 vagy újabb
- [uv](https://docs.astral.sh/uv/)
- botfelhasználóval rendelkező Discord-alkalmazás
- fejlesztéshez erősen ajánlott egy külön tesztszerver

## A Discord-alkalmazás beállítása

1. Hozz létre egy alkalmazást a Discord Developer Portalon.
2. Az **Installation** oldalon engedélyezd a **Guild Install** lehetőséget.
3. Add hozzá az `applications.commands` és `bot` telepítési scope-okat.
4. A jelenlegi verzióhoz nem szükséges privilegizált Gateway intent.
5. Adj a botnak **View Channels** és **Manage Channels** jogosultságot, majd
   telepítsd egy tesztszerverre. Ne adj neki `Administrator` vagy `Manage Roles`
   jogosultságot.
6. A bot parancsait jelenleg csak Discord **Administrator** jogosultsággal
   rendelkező tagok használhatják. Ezt a parancscsoport is deklarálja, a bot
   pedig futás közben központilag is ellenőrzi.
7. Kurzus létrehozása előtt engedélyezd a Discord **Community** funkcióját a
   szerveren. Az alapértelmezett kurzussablon fórumcsatornát tartalmaz, ehhez
   Community szükséges.

Ne adj `Administrator` jogosultságot a botnak. A későbbi adminisztrációs
funkcióknál csak akkor dokumentálunk további jogosultságot, amikor arra valóban
szükség lesz.

A felhasználók korlátozása és a bot saját jogosultságai két külön dolog: az
adminisztrátorok futtathatják a parancsokat, miközben a bot továbbra is csak az
aktuális funkciókhoz ténylegesen szükséges jogosultságokat kapja meg.

## Telepítés

Hozd létre a projekthez tartozó `.venv` környezetet, és telepítsd bele a zárolt
függőségeket:

```bash
uv sync
cp .env.example .env
```

Szerkeszd a `.env` fájlt, és add meg a bot tokenjét és a tesztszerver azonosítóját:

```dotenv
DISCORD_TOKEN=your_real_bot_token
DISCORD_GUILD_ID=123456789012345678
DISCORD_COMMAND_SYNC=guild
LOG_LEVEL=INFO
DISCORD_CONFIG_PATH=config.yaml
DISCORD_DATABASE_PATH=data/bot.db
```

A `.env` fájlt soha ne commitold, a bot tokenjét pedig ne oszd meg. Ha a token
kiszivárog, azonnal cseréld le.

## Futtatás

```bash
./run.sh
```

Az adminisztrációs munkamenet végén állítsd le a botot `Ctrl+C`-vel. A helyi
SQLite adatbázis a `data/` könyvtárba kerül, és szándékosan nincs Gitben követve.
Az első `0.4.0` vagy újabb indításkor a meglévő adatbázis helyben megkapja az
új, közös csatornákat nyilvántartó táblákat; a meglévő szemeszterek,
kurzusok, erőforrás-azonosítók és szinkronpillanatképek megmaradnak. Ettől
függetlenül az első éles indítás előtt ajánlott másolatot készíteni a
`data/bot.db` fájlról.

## Első használat

1. Állítsd be a `DISCORD_COMMAND_SYNC=guild` értéket, és egyszer indítsd el a
   botot, hogy a parancsok regisztrálódjanak Discordon.
2. Futtasd a `/server status` parancsot, és ellenőrizd, hogy a Community és a
   Manage Channels értéke egyaránt `yes`.
3. Hozz létre egy szemesztert, például: `/semester create name:2026-fall`.
4. Hozz létre egy kurzust, például: `/course create name:Machine Learning
   semester:2026-fall code:ML01`.
5. Ellenőrizd a `/course info name:Machine Learning` paranccsal.
6. Kézi Discord-módosítás után futtasd a `/course sync name:Machine Learning`
   parancsot, vagy a `name` elhagyásával szinkronizáld az összes kezelt kurzust.
7. A törlési és tömeges műveleteket először megerősítés nélkül nézd meg. Csak a
   privát előnézet átnézése után ismételd meg `confirm:true` értékkel.

A kurzus létrehozásakor egy szemeszterrel megjelölt kategória és a következő
struktúra készül:

```text
2026-fall · Machine Learning
├── #course-chat
├── discussions (fórum)
└── study-room (hang)
```

A fórumcímkék, csatornanevek, témák és a kategória formátuma a `config.yaml`
fájlból származik. Az alapértelmezett `{semester} · {course_name}` formátummal a
Discord csatornalistájában több szemeszter kurzusai is egyértelműen
megkülönböztethetők.

Az alapértelmezett szerkezet szándékosan csak három csatornából áll:

- A `#course-chat` a gyors beszélgetések, rövid élettartamú közlemények és a
  kapcsolódó fórumbejegyzések hivatkozásainak helye.
- A `discussions` a tartós, kereshető kérdések, források, feladatok, vizsgák,
  jegyzetek, kódok, projektek és ötletek helye. A hozzájuk illő címkékkel
  maradnak rendezettek a bejegyzések. Egy fórumbejegyzést be lehet linkelni a
  `#course-chat` csatornába, miközben a részletes beszélgetés a bejegyzés alatt
  marad.
- A `study-room` a kurzus hangcsatornája.

Az alapértelmezett sablonban nincs külön `#materials` csatorna. Felügyelt,
csak olvasható jogosultságmodell nélkül ez valószínűleg egy újabb rendezetlen
hírfolyammá válna, miközben a fórum `Resource`, `Notes` és `Important`
címkéivel az anyagok könnyebben megtalálhatók. Kurzusonkénti random csatorna
sincs; erre használj egy kézzel kezelt globális közösségi csatornát, például a
`#random` csatornát. Mindkét döntést később felülvizsgálhatjuk, ha a valós
használat alapján szükség lesz rá.

## Parancsok

Minden válasz privát, és minden parancshoz Discord `Administrator` jogosultság
szükséges a parancsot futtató felhasználónál.

- `/server status` — kapcsolat, előfeltételek, jogosultságok és kezelt objektumok
  darabszáma.
- `/semester create name:<név>` — helyi kezelt szemeszter létrehozása. Discord
  kategóriát nem hoz létre.
- `/semester list` — a szerver kezelt szemesztereinek listázása.
- `/semester delete name:<név> [confirm:true]` — üres helyi szemeszterrekord
  előnézete, majd törlése. Ha kurzus van benne, a bot megtagadja a műveletet.
- `/course create name:<név> semester:<szemeszter> [code:<kód>]` — a konfigurált
  Discord-kurzusstruktúra létrehozása és azonosítóinak mentése.
- `/course list [semester:<szemeszter>]` — minden kezelt kurzus listázása vagy
  szűrés szemeszter szerint.
- `/course info name:<név>` — az eltárolt Discord-erőforrásazonosítók és a
  létrehozási állapot megjelenítése.
- `/course sync [name:<név>]` — a Discord aktuális állapotának elfogadása és helyi
  pillanatképének mentése egy kurzusnál, illetve a `name` elhagyásakor minden
  kezelt kurzusnál, a Discord módosítása nélkül.
- `/course delete name:<név> [confirm:true]` — előnézet, majd a kurzus stabil
  ID-val nyilvántartott erőforrásainak és helyi rekordjának törlése, a kézi
  csatornák megtartásával.
- `/course channel add-all name:<név> channel_type:<Text|Forum|Voice>
  [topic:<téma>] [confirm:true]` — közös csatorna előnézete, majd létrehozása és
  nyilvántartása minden kezelt kurzusban.
- `/course channel delete-all name:<név> [confirm:true]` — előnézet, majd csak az
  adott közös csatornához korábban eltárolt stabil ID-k törlése.
- `/course channel list` — a közös definíciók és a hozzájuk jelenleg nyilvántartott
  kurzuscsatornák darabszámának listázása.

A kurzus- és szemeszternevek összehasonlítása nem érzékeny a kis- és nagybetűkre.
Egy befejezett létrehozási művelet ismétlése nem készít másolatot. Ha a Discord
részben hibázik, a sikeresen létrehozott erőforrások azonosítói megmaradnak, és
ugyanaz a parancs folytatja a hiányos kurzust. Az ismeretlen kategóriákat és
csatornákat a bot ütközésként jelzi; nem törli és nem veszi át őket automatikusan.

### Mit csinál a kurzusszinkronizálás?

A `/course sync` számára a Discord az elsődleges állapot. Akkor is működik, ha a
kézi változtatások idején a bot nem futott: utána indítsd el, majd futtasd a
parancsot. A művelet:

- stabil Discord-azonosítókat követ, ezért automatikusan elfogadja az ismert
  kategóriák és csatornák kézi átnevezését vagy áthelyezését;
- helyileg elmenti a kezelt kurzusban jelenleg látott neveket, típusokat,
  kategória-elhelyezést és további csatornákat;
- megtartja és a pillanatképben rögzíti a kézzel létrehozott további csatornákat,
  de nem rendel hozzájuk automatikusan sablonszerepet;
- egy törölt, majd újra létrehozott kategóriát vagy sabloncsatornát csak akkor
  kapcsol vissza, ha az elvárt név és típus pontosan egy egyértelmű találatot ad;
- jelzi a hiányzó, eltérő típusú vagy nem egyértelmű erőforrásokat, hogy az
  adminisztrátor átnézhesse őket;
- soha nem hoz létre, nevez át, helyez át vagy töröl Discord-erőforrást.

A `name` nélküli `/course sync` minden, a bot által már kezelt kurzust átvizsgál.
A szerver ettől független részeit szándékosan nem sajátítja ki és nem leltározza.
Egy további csatorna biztonságosan megmaradhat egy kezelt kurzuskategóriában, de
ettől nem válik automatikusan a sablon egyik kötelező csatornájává.
A slash parancsok paramétereként használt logikai kurzusnév akkor sem változik
meg, ha a Discord-kategóriát kézzel átnevezed.

Ez biztonságos együttműködést garantál, nem minden lehetséges kézi módosítás
automatikus értelmezését. Amíg a bot offline, nem történik azonnali
szinkronizálás. Elindítás után a `/course sync` elfogadja az ismert azonosítójú
változást, visszakapcsol egyetlen egyértelmű pótlást, vagy a Discord módosítása
nélkül jelzi a megoldatlan eltérést. Kézi módosítás után és későbbi
életciklus-műveletek előtt futtasd le.

A bot nem tud automatikusan helyreállni, ha elveszik a helyi adatbázisa,
eltávolítják a szerverről, visszaállítják a tokenjét a `.env` frissítése nélkül,
vagy elveszik a szükséges láthatóságát és jogosultságait. Több hasonló pótlás
között sem találgathat biztonságosan. Ezek a helyzetek hiányzó vagy nem
egyértelmű eredményt adnak, illetve kézi beállítást igényelnek; romboló javítást
nem engednek.

Jelenleg nincs archiválási, visszaállítási vagy a Discordot módosító
szinkronizálási parancs. Törlés csak az alább dokumentált, szűk célú, előnézetes
parancsokkal lehetséges.

## Közös csatornák minden kurzusban

Ezt használd, ha minden jelenlegi és jövőbeli kezelt kurzushoz ugyanaz a további
csatorna kell. Először kérj előnézetet:

```text
/course channel add-all name:announcements channel_type:Text topic:Shared announcements
```

Az előnézet felsorolja, mely kurzusoknál hozna létre vagy kapcsolna vissza
csatornát, mit hagyna ki, illetve hol van ütközés. Ekkor még semmi nem változik.
Ha megfelelő, ismételd meg megerősítéssel:

```text
/course channel add-all name:announcements channel_type:Text topic:Shared announcements confirm:true
```

A definíció az SQLite-adatbázisba kerül. A meglévő kezelt kurzusok megkapják a
csatornát, ahol elérhető a kategóriájuk, és a későbbi `/course create` műveletek
is létrehozzák. A parancs biztonságosan ismételhető: az élő, nyilvántartott
csatornákat nem duplikálja. Azonos nevű, nem nyilvántartott vagy nem egyértelmű
csatornánál automatikus átvétel helyett ütközést jelez. Az alapsablon által már
használt csatornanevet elutasítja. A fórumhoz Community szükséges;
hangcsatornának nem lehet témája.

A tárolt közös definíciókat bármikor lekérdezheted a `/course channel list`
paranccsal.

Az adott közös csatorna eltávolításához először kérj előnézetet, majd erősítsd meg:

```text
/course channel delete-all name:announcements
/course channel delete-all name:announcements confirm:true
```

A törlés kizárólag a közös definícióhoz eltárolt Discord ID-kat célozza, akkor
is, ha a nyilvántartott csatornát kézzel átnevezték vagy áthelyezték. Egy kézzel
létrehozott, azonos nevű csatornát nem választ ki. A sikeres kapcsolatok a művelet
közben törlődnek a nyilvántartásból; részleges Discord-hiba után a parancs
ismétlése csak a hátralévő munkát folytatja. Befejezés után az új kurzusok már nem
kapják meg ezt a definíciót.

## Biztonságos törlés

A kurzustörlés mindig kétlépcsős:

```text
/course delete name:Machine Learning
/course delete name:Machine Learning confirm:true
```

A privát előnézet felsorolja az élő nyilvántartott erőforrásokat, a már hiányzó
elemeket, a megtartandó kézi/nem nyilvántartott csatornákat, és azt, hogy a
kategória törlődik-e. Minden stabil ID-val nyilvántartott sablon- és közös
csatorna a megerősített törlés célpontja, akkor is, ha kézzel átnevezték vagy
máshová helyezték. Ismeretlen csatornát a bot soha nem töröl. Ha a
kurzuskategóriában kézi csatorna marad, a kategória megmarad és nem kezelt
kategóriává válik; az üres kategória törlődik. A helyi kurzusrekord csak az összes
szükséges Discord-törlés sikere után tűnik el. Részleges hiba esetén megmarad a
biztonságos újrapróbáláshoz.

Szemeszter csak azután törölhető, hogy minden kezelt kurzusa eltűnt:

```text
/semester delete name:2026-fall
/semester delete name:2026-fall confirm:true
```

A szemesztertörlés csak az üres helyi szemeszterrekordot távolítja el; nem töröl
Discord-erőforrást, és nem törli automatikusan a kurzusokat.

## A kurzussablon konfigurálása

A `config.yaml` séma verziója `1`. A `course_template.category.name` határozza
meg a kategória nevét. A `course_template.channels` minden eleme rendelkezik egy
stabil belső kulccsal, valamint megadja a látható `name` értéket és a csatorna
`type` típusát (`text`, `forum` vagy `voice`). A szöveg- és fórumcsatornáknak
lehet `topic` mezője, a fórumok pedig legfeljebb 20 egyedi `tags` címkét
tartalmazhatnak.

A nevekben és témákban ezek a helyőrzők használhatók:

- `{course_name}`
- `{course_code}`
- `{semester}`

Az alapértelmezett kategóriabeállítás:

```yaml
course_template:
  category:
    name: "{semester} · {course_name}"
```

Ez az újonnan létrehozott kurzusokra érvényes. A meglévő kezelt kategóriákat a
bot nem nevezi át automatikusan, mert a Discord állapota az elsődleges. Ha
szeretnéd, nevezd át őket kézzel, majd a `/course sync` paranccsal fogadtasd el
az aktuális nevet. Az elkészült kategórianévnek bele kell férnie a Discord 100
karakteres korlátjába.

A konfiguráció ellenőrzése még a Discord-csatlakozás előtt megtörténik. Az
ismétlődő YAML-kulcsok, nem támogatott típusok, hibás helyőrzők, duplikált
címkék és hibás kötelező mezők leállítják az indulást, mielőtt a bot bármit
módosítana Discordon.

## Parancsszinkronizálás

A `DISCORD_COMMAND_SYNC` teszi szabályozottá a parancsok regisztrálását:

- `guild`: a parancsokat a `DISCORD_GUILD_ID` szerverre másolja és szinkronizálja;
  fejlesztés közben ezt használd, mert a szerverparancsok gyorsan frissülnek;
- `global`: globálisan szinkronizálja a parancsokat a telepített szerverekhez;
- `off`: a bot a regisztrált parancsok módosítása nélkül csatlakozik.

A parancsok regisztrálása után `off` értékkel elkerülhető a felesleges
szinkronizálás minden helyi indításkor.

## Tesztek

```bash
uv run python -m unittest discover -s tests
```

A tesztcsomag offline fut: Discord-kapcsolat nélkül ellenőrzi a konfigurációt, a
parancsregisztrációt, az adminisztrátori jogosultság-ellenőrzést, a sablon
feldolgozását, az SQLite-adatmentést, valamint a kurzuslétrehozási,
szinkronizálási, közöscsatorna- és biztonságos törlési folyamatokat. A felhasználói
működés módosítása után továbbra is ajánlott egy utolsó próba külön
Discord-tesztszerveren.

## Biztonság és helyi állapot

- A botnak nincs szüksége Discord `Administrator` jogosultságra. A jelenlegi
  módosító műveletéhez csak `View Channels` és `Manage Channels` kell.
- Minden parancs ellenőrzi azt is, hogy a parancsot futtató tag
  szerveradminisztrátor-e. Ezt a Discord alapértelmezett parancsjogosultsága is
  jelzi, és egy központi futásidejű ellenőrzés második védelmi rétegként
  kikényszeríti.
- A parancsválaszok és hibák privátak, ezért a szokásos kimenetet csak a
  parancsot kiadó adminisztrátor látja.
- A bot nem olvassa az üzenetek tartalmát, és nem kér privilegizált Gateway
  intenteket.
- A romboló parancsok változtatás nélküli előnézetet, majd `confirm:true`
  megerősítést kérnek. Csak a bot stabil ID-val birtokolt elemeit célozzák, és
  névegyezés miatt soha nem törölnek vagy vesznek át csendben ismeretlen
  Discord-kategóriát vagy -csatornát.
- A `data/bot.db` a bot helyi, kezelt állapotadatbázisa. Szemesztereket,
  kurzusokat, létrehozási állapotokat és stabil Discord-erőforrásazonosítókat
  tárol. Nem a Discord-üzenetek vagy a szerver tartalmának biztonsági mentése.
- Az adatbázist és az SQLite kísérőfájljait a Git figyelmen kívül hagyja. Későbbi
  nagyobb adminisztrációs vagy életciklus-műveletek előtt készíts másolatot a
  `data/bot.db` fájlról. Valódi szerveren ne töröld könnyelműen: a jelenlegi
  verzió még nem tudja a meglévő Discord-csatornákból egyeztetéssel vagy
  átvétellel újraépíteni a tulajdonosi állapotot.
- Ha a kurzus létrehozása néhány erőforrás elkészítése után megszakad, azok
  azonosítóit a bot lehetőség szerint elmenti. A válasz felsorolja a létrehozott
  elemeket, ugyanannak a `/course create` parancsnak az ismétlése pedig megpróbálja
  folytatni a hiányos kurzust.
- Ha egy félbehagyott kurzus során létrehozott csatornát kézzel áthelyezel, a
  kurzuslétrehozás ismétlése stabil azonosító alapján felismeri és a választott
  helyén hagyja, miközben elkészíti a többi hiányzó erőforrást.
- A közöscsatorna- és kurzustörlés menti az előrehaladást. Discord-hiba után
  olvasd el az eredményt, majd ismételd meg ugyanazt a megerősített parancsot; a
  már eltávolított ID-k kimaradnak, a megmaradt adatbázisrekord pedig védi a
  hátralévő munkát.
- A kezelt csatornák kézi módosítása után futtasd a `/course sync` parancsot. Az
  áthelyezést és átnevezést elfogadja, az egyértelmű pótlásokat visszakapcsolja, a
  megoldatlan eltéréseket pedig a Discord módosítása nélkül jelzi.
- Használat után a bot `Ctrl+C`-vel leállítható. A korábban létrehozott
  Discord-erőforrások és a helyi SQLite-állapot megmaradnak.

## Hibaelhárítás

### A bot nem indul el

- Először futtasd az `uv sync` parancsot, majd a botot a `./run.sh` paranccsal
  indítsd. Így biztosan a projekt saját `.venv` környezete használatos, nem a
  rendszer Python-telepítése.
- Ellenőrizd, hogy a `.env` bot tokent tartalmaz, nem Application ID-t. A token a
  Discord Developer Portal **Bot** oldalán hozható létre vagy állítható vissza.
- A konfigurációs hibákat a program csatlakozás előtt jelzi. Ellenőrizd a
  `DISCORD_CONFIG_PATH` és `DISCORD_DATABASE_PATH` útvonalát, a `config.yaml`
  módosításait pedig vesd össze a dokumentált sémával és helyőrzőkkel.
- A valódi tokent soha ne másold hibajegybe, commitba, képernyőképbe vagy
  beszélgetésbe. Ha kiszivárgott, állítsd vissza a Developer Portalon, majd
  frissítsd a `.env` fájlt.

### Nem jelennek meg a slash parancsok

- Fejlesztéshez állítsd be a `DISCORD_COMMAND_SYNC=guild` értéket, ellenőrizd,
  hogy a `DISCORD_GUILD_ID` annak a szervernek az azonosítója, amelyre a botot
  telepítetted, majd egyszer indítsd újra a botot.
- Ellenőrizd, hogy a telepítés a `bot` és az `applications.commands` scope-ot is
  tartalmazza.
- Hagyd futni a folyamatot addig, amíg a napló sikeres csatlakozást és
  szinkronizálást jelez. A regisztráció után a szokásos indításokhoz megfelelő a
  `DISCORD_COMMAND_SYNC=off` érték.

### Egy parancs nem érhető el vagy elutasítást kap

- A parancsot futtató személynek Discord `Administrator` jogosultsággal kell
  rendelkeznie. Ez nem jelenti azt, hogy magának a botnak is `Administrator`
  jogosultságot kell adni.
- A botnak `View Channels` és `Manage Channels` jogosultság kell a célként
  használt szerveren. A csatorna- vagy kategória-felülírások és a botszerepkör
  helye ettől még befolyásolhatja, hogy mit lát vagy módosíthat.
- Az aktuálisan észlelt előfeltételekhez és kezelt darabszámokhoz futtasd a
  `/server status` parancsot.

### A kurzus létrehozása sikertelen

- Először hozd létre a szemesztert a `/semester create` paranccsal.
- Engedélyezd a Discord Community funkcióját, mert az alapértelmezett sablon
  fórumcsatornát tartalmaz.
- Ellenőrizd, van-e már az elvárt névvel nem kezelt kategória vagy csatorna. A
  bot ezt módosítás helyett ütközésként jelzi.
- Ha a válasz részleges létrehozást jelez, ne készítsd el rögtön kézzel ugyanazokat
  az elemeket. Javítsd a jogosultsági vagy konfigurációs problémát, majd ismételd
  meg ugyanazt a parancsot, hogy a bot a tárolt azonosítóktól folytathassa.
- Ha a kezelt csatornákat kézzel törölték vagy átrendezték, tartsd meg az
  adatbázist, és futtasd a `/course sync name:<kurzus>` parancsot. Nézd át a
  hiányzó vagy nem egyértelmű találatokról szóló figyelmeztetést; az adatbázis
  törlése eltávolíthatja az egyetlen helyi tulajdonosi nyilvántartást.

### Egy tömeges vagy törlési művelet ütközést vagy részleges hibát jelez

- Kézi módosítás után futtasd újra a parancsot `confirm:true` nélkül, hogy friss
  előnézetet kapj.
- Az azonos nevű, nem nyilvántartott csatorna szándékosan ütközés. Nevezd át,
  vagy válassz másik közös csatornanevet az automatikus átvétel helyett.
- Ha a Discord csak néhány létrehozást vagy törlést tagadott meg, javítsd a
  jogosultságot, majd ismételd meg a megerősített parancsot. A tárolt ID-k miatt
  a már elvégzett munka nem lesz név alapján megcélozva vagy vakon duplikálva.
- Kézi csatornát tartalmazó kurzuskategória szándékosan megmarad a kurzus
  törlése után. Ezek a csatornák és a kategória ezután nem kezelt elemek.

## Dokumentációs szabály

A `README.md` és a `README.hu.md` a projekt használati kézikönyvei. Minden
jövőbeli, felhasználó által érzékelhető változásnak ugyanabban a módosításban
frissítenie kell mindkettőt: a használatot, jogosultságokat, konfigurációt,
példákat, mellékhatásokat, biztonsági megjegyzéseket, tesztelést és
hibaelhárítást is. A két változatnak tartalmilag egyenértékűnek kell maradnia.

Az alábbi ütemterv a később újra elővehető ötletek tartós emlékezete. Nem jelent
automatikus megvalósítási vállalást: új munkát csak az aktuális, kifejezett
felhasználói kérés engedélyez. Az ötleteket nem dobjuk el csendben; a
megvalósított elemek átkerülnek a jelenlegi funkciók dokumentációjába, az
elvetett vagy kiváltott elemek mellett pedig rövid megjegyzés marad, hacsak a
felhasználó nem kéri kifejezetten a törlésüket.

## Ütemterv és jövőbeli lehetőségek

Jelenlegi állapot: a `0.4.1` verzió adminisztrátoroknak szánt
szemeszterkezelést, sablonvezérelt kurzuslétrehozást és -lekérdezést, helyi,
stabil azonosítós állapotmentést, biztonságos ütközéskezelést és
szerverdiagnosztikát, valamint a Discord állapotát elsődlegesnek tekintő,
Discordot nem módosító kurzusszinkronizálást tartalmaz. Emellett kezelt kurzusok
és üres szemeszterek előnézetes törlését, valamint minden jelenlegi és jövőbeli
kurzusra érvényes, nyilvántartott közös csatornákat is kezel. Az alábbi munkák
opcionálisak, és külön, kifejezett kérés szükséges hozzájuk.

A `0.4.1` alapértelmezetten látható szemeszter-előtagot ad az új
kurzuskategóriákhoz, és a fent dokumentált, célzott háromcsatornás
kurzusstruktúrát használja.

### 1. prioritás — a biztonságos szinkronizálási alap bővítése

- Elkészült a `0.3.0` verzióban: a `/course sync` elfogadja a Discord aktuális
  kurzusállapotát, pillanatképet ment, csak egyértelmű találatot kapcsol vissza,
  és a Discord módosítása nélkül jelzi az eltéréseket.
- Külön próbaüzemű terv hozzáadása, mielőtt bármely jövőbeli lehetőség
  visszaalkalmazhatná a sablont a Discordra.
- Vezetett feloldás a nem egyértelmű találatokhoz és részletesebb előzmények a
  szinkronizálási pillanatképek között.

### 2. prioritás — a szemeszter- és kurzuséletciklus bővítése

- Elkészült a `0.4.0` verzióban: kezelt kurzusok és üres szemeszterek szűk célú,
  előnézetes törlése, az ismeretlen/kézi erőforrások megtartásával.
- Kurzus archiválása és visszaállítása azonnali végleges törlés nélkül.
- Szemeszter-információ, aktuális szemeszter kijelölése, archiválás és
  visszaállítás.
- Annak pontos meghatározása, mit változtat az archiválás Discordon, és mi marad
  meg az SQLite-adatbázisban.

### 3. prioritás — használhatóság, helyreállítás és hordozhatóság

- Automatikus kiegészítés a szemeszter- és kurzusparaméterekhez.
- Az egyeztetés kiterjesztése a hiányzó adatbázis helyreállítására; a jelenlegi
  szinkronizálás csak akkor tud egyértelmű pótlást visszakapcsolni, ha a kurzus
  nyilvántartása még létezik.
- A kezelt állapot exportálása/importálása és dokumentált mentési/visszaállítási
  eljárás.

### 4. prioritás — jogosultságok és tömeges adminisztráció

- Elkészült a `0.4.0` verzióban: közös csatorna előnézetes hozzáadása és törlése
  minden kurzusban, az új kurzusokra is elmentve, kizárólag stabil ID-alapú
  törléssel.
- Hallgatói szerepkörök és konfigurálható jogosultságsablonok.
- Óvatos jogosultság-szinkronizálás, először vizsgálattal és próbaüzemmel.
- Opcionális, felügyelt és csak olvasható materials csatorna megfontolása a
  szerepkör- és jogosultságsablonok elkészülte után; ez ma szándékosan nem
  része az alapértelmezett kurzussablonnak.
- Ellenőrzött, tömeges szemeszter-/kurzusimport előzetesen átnézett CSV- vagy
  YAML-tervből.
- Opcionális globális szerverstruktúra-beállítás, miután annak tulajdonosi
  határait meghatároztuk.

### 5. prioritás — üzemeltetési megerősítés

- Szerverenkénti műveleti zárak az egymással átfedő módosítások megelőzésére.
- Sorrendi SQLite-sémamigrációk és sablonverzió-/pillanatkép-követés.
- Részletesebb auditnaplózás a tokenek és más titkok további kitakarásával.
- Minden jövőbeli, szélesebb visszaállítás vagy kaszkádos törlés maradjon külön a
  jelenlegi szűk törlési parancsoktól, előnézettel, kifejezett megerősítéssel és
  egyértelmű helyreállítási korlátokkal.

## Projektkontextus

A hosszú távú termék- és mérnöki háttéranyag a
[docs/project-context.md](docs/project-context.md) fájlban található. Irányt mutat,
de nem kötelező funkciólista.

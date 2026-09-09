# Discord Bot

Igény szerint, helyben futtatott Discord-szerveradminisztrációs eszköz egy MSc
hallgatói közösség számára. Az adminisztrátor elindítja, amikor szüksége van rá,
majd a munka végeztével leállítja. A bot által később létrehozott Discord-erőforrások
offline állapotban is megmaradnak.

A jelenlegi alapverzió részei:

- környezeti változókon alapuló konfiguráció;
- minimális, nem privilegizált Gateway intentek;
- szabályozható szerver- vagy globális alkalmazásparancs-szinkronizálás;
- biztonságos helyi naplózás;
- minden parancsra érvényes, központi adminisztrátori jogosultság-ellenőrzés;
- privát `/server status` parancs.

A kurzus-, szemeszter-, szerepkör-, szinkronizálási és adatbázisfunkciók még
nincsenek megvalósítva.

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
5. Telepítsd az alkalmazást egy tesztszerverre. A jelenlegi státuszparancshoz a
   botnak nincs szüksége széles körű jogosultságokra.
6. A bot parancsait jelenleg csak Discord **Administrator** jogosultsággal
   rendelkező tagok használhatják. Ezt a parancscsoport is deklarálja, a bot
   pedig futás közben központilag is ellenőrzi.

Alapértelmezetten ne adj `Administrator` jogosultságot a botnak. A későbbi
adminisztrációs funkcióknál külön dokumentáljuk majd a ténylegesen szükséges
jogosultságokat.

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
```

A `.env` fájlt soha ne commitold, a bot tokenjét pedig ne oszd meg. Ha a token
kiszivárog, azonnal cseréld le.

## Futtatás

```bash
./run.sh
```

Használd a `/server status` parancsot a beállított Discord-szerveren. Az
adminisztrációs munkamenet végén állítsd le a botot `Ctrl+C`-vel.

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

## Projektkontextus

A hosszú távú termék- és mérnöki háttéranyag a
[docs/project-context.md](docs/project-context.md) fájlban található. Irányt mutat,
de nem kötelező funkciólista.

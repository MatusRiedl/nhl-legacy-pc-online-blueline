"""Where things live in a roster of the community family: "ROSTER2526", its descendants such as the
community's 2026-27 roster, and the rosters this program makes from them.

The game has 252 fixed team slots in 16 fixed leagues. The updater never adds a team and never
changes a team's league (hard limits of the game); it only refills existing slots.
"""
import re
import unicodedata
from collections import Counter

# ttOk.league
LEAGUE_NAMES = {0: 'NHL', 1: 'AHL', 2: 'SHL', 3: 'Liiga', 4: 'DEL', 5: 'Extraliga', 6: 'National League',
                7: 'Norway', 8: 'National', 9: 'OHL', 10: 'QMJHL', 11: 'WHL', 12: 'Top Prospects',
                13: 'Custom', 14: 'Winter Classic', 15: 'EASHL'}
CUSTOM_LEAGUE = 13
TEAM_COUNT = 252
MAX_PER_TEAM = 40                 # roster entry ids (ulGe.key) are team * 40 + slot
XWOT_UNSET = (1 << 14) - 1

# NHL.com team code -> team slot. Slot 22 is the old Arizona slot (holds Utah); Seattle and Vegas
# live in the two All-Star slots.
API_TO_SLOT = {'ANA': 0, 'WPG': 1, 'BOS': 2, 'BUF': 3, 'CGY': 4, 'CAR': 5, 'CHI': 6, 'COL': 7, 'CBJ': 8,
               'DAL': 9, 'DET': 10, 'EDM': 11, 'FLA': 12, 'LAK': 13, 'MIN': 14, 'MTL': 15, 'NSH': 16,
               'NJD': 17, 'NYI': 18, 'NYR': 19, 'OTT': 20, 'PHI': 21, 'UTA': 22, 'PIT': 23, 'STL': 24,
               'SJS': 25, 'TBL': 26, 'TOR': 27, 'VAN': 28, 'WSH': 29, 'SEA': 30, 'VGK': 31}
SLOT_TO_API = {v: k for k, v in API_TO_SLOT.items()}
# custom-team copies of NHL teams with current branding; they must mirror their primary team
MIRRORS = {0: [225], 2: [223], 5: [232], 12: [230], 13: [227], 14: [233], 20: [231], 22: [229],
           24: [222], 28: [224], 30: [228], 31: [226]}
MIRROR_OF = {m: p for p, ms in MIRRORS.items() for m in ms}
# what the community calls those copies; a roster whose copies are out of step with their NHL team
# (the 2026-27 community roster) is still recognised by these names
MIRROR_NAMES = {222: 'Blues', 223: 'Bruins', 224: 'Canucks', 225: 'Ducks', 226: 'Golden Knights', 227: 'Kings',
                228: 'Kraken', 229: 'Mammoth', 230: 'Panthers', 231: 'Senators', 232: 'Whalers', 233: 'Wild'}

NHL_PRIMARY = set(range(32))
NHL_ALL = NHL_PRIMARY | set(MIRROR_OF)
AHL = set(range(32, 62)) | {234, 235}   # Coachella Valley and Henderson sit in custom slots
NATIONAL = set(range(133, 154))   # 133 Austria, 134 Belarus, 135 Canada ... 153 USA (132 is a club)
# NHL teams and AHL clubs (the NHL organisations; every league's clubs hold contracts: CONTRACT_CLUB)
CLUB = set(range(62)) | {234, 235}
# the club leagues' slots (ttOk.league 2-7 and 9-11)
SHL = set(range(62, 76))
LIIGA = set(range(76, 91))
DEL = set(range(91, 105))
EXTRALIGA = set(range(105, 119))
NL = set(range(119, 131))
NORWAY = {131, 132}
EUROPE = SHL | LIIGA | DEL | EXTRALIGA | NL | NORWAY
OHL = set(range(154, 174))
QMJHL = set(range(174, 192))
WHL = set(range(192, 214))
CHL = OHL | QMJHL | WHL
EVENTS = set(range(214, 222))     # Top Prospects, Winter Classic, EASHL: left alone
SPARE = range(236, 252)           # custom slots switched off in the base: room for displaced prospect pools
# the Penticton Vees (owner, 2026-11-02): the last spare slot (pools fill from the low end, Create a Team takes the first
# free one). A named custom team on every roster, a club of the WHL's B.C. Division on a roster for the patched game
# (gamepatch.LEAGUE_SLOTS). VEES_RINK: Prince George, whose arena row they copy (ice and boards) and whose jerseys they borrow
VEES, VEES_RINK = 251, 204
# Jokerit and Jukurit (owner, 2026-11-26, a tester's ask): the two Liiga clubs the game has no slot for, in the two spare slots
# below the Vees; clubs of the Liiga on a roster for the patched game (gamepatch.LEAGUE_SLOTS), named custom teams on the
# unpatched one. Jokerit wears art 87, whose old logos, centre ice, arena, banner and puck are still on the disc
JOKERIT, JUKURIT = 249, 250


class Extra:
    """A club the data pack lists under its league's `extra` (no slot in the game) that has a custom slot of its own:
    `league` the data pack's league key, `code` its art code (ttOk RPbr, the data pack's `art`), `city` what is written as
    its city (as its league's clubs in the data pack: a WHL club's town, a Liiga club's short name), `where` the league the
    window lists it under, `rink` the club whose arena row it starts on (ice and boards),
    `arena` (name, city, capacity) of its own building, `logo` a logo link of its own (None: the data pack's)."""

    def __init__(self, league, code, city, where, rink, arena, logo=None):
        self.league, self.code, self.city, self.where = league, code, city, where
        self.rink, self.arena, self.logo = rink, arena, logo


# 'disc:87': art 87's own logo from the player's disc (art/install.disc_logo), the old jester the tester asked for
EXTRA_CLUBS = {JOKERIT: Extra('liiga', 'JOK', 'Jokerit', 'Liiga', 80, ("Veikkaus Arena", "Helsinki", 13349), 'disc:87'),
               JUKURIT: Extra('liiga', 'JUK', 'Jukurit', 'Liiga', 80, ("Let's Go Areena", "Mikkeli", 4200)),
               VEES: Extra('chl', 'PEN', 'Penticton', 'WHL', VEES_RINK,
                           ("South Okanagan Events Centre", "Penticton, BC", 4494))}
# the base roster keeps its NHL "System" prospect pools here (DEL 101-104, Extraliga, National League)
SYSTEM_POOL_SLOTS = set(range(101, 131))
# teams whose players hold a contract with the team (owner, 2026-10-22: "this tool is a tool to actually make it happen for
# players to have contracts"): every club of every league, Coachella Valley / Henderson and the spare custom slots (a
# player's own teams); prospect pools in those slots are left out by contracts.contract_clubs. Not the national teams,
# the event teams or the NHL copies 222-233.
CONTRACT_CLUB = set(range(133)) | CHL | {234, 235} | set(SPARE)
# farm teams the NHL team table cannot name (ttOk.ahlaffiliate has six bits): Coachella Valley -> Seattle,
# Henderson -> Vegas
AHL_PARENT_EXTRA = {234: 30, 235: 31}
# art ids of their own for Coachella Valley and Henderson: the community roster's 20073 / 20081 (create-a-team logos 72 /
# 80, art/crests.py) on every roster; the game's own roster has 20054, which every switched-off custom team shows. Lab
# round 34 (2026-10-19): a free art id of the NHL kind (900 / 901, the owner's first
# wish) gives a custom slot a blue square on the ice and the jersey, because the game draws custom slots from the
# create-a-team files whatever the art id; with 20073 / 20081 and the crests the photos install, both teams show their
# own crest (docs/notes/lab-round-34.md). Only the team table's artid holds a team's art id.
OWN_ART = {234: 20073, 235: 20081, VEES: 20085, JOKERIT: 20086, JUKURIT: 20087}     # Jokerit, Jukurit: logos 85 / 86
# and on a roster for the patched game (0.50.4, lab round 48): art 900 / 901 as a club of the AHL, the created-team flag off
# (ttOk BERR `table` 0) and the jersey rows (`stockteamjerseys`) of a donor club, whose files art/clubart.py clones. Lab round
# 34's blue square was the flag left on, with no rows and no files. CLUB_DONOR: slot -> (the donor's art id, its variants)
CLUB_ART = {234: 900, 235: 901, VEES: 902, JOKERIT: 87, JUKURIT: 903}
# Charlotte's, Utica's, Prince George's, Ilves's (two digits as 87), Providence's (the donor's art id has as many digits)
CLUB_DONOR = {234: (162, (3, 4)), 235: (141, (0, 1)), VEES: (373, (2, 3)), JOKERIT: (86, (4, 5)), JUKURIT: (150, (2, 3))}
# club art ids the disc has files of its own for (87: logos, centre ice, arena, banner, puck, goalie helmet): those files stay
# the disc's, only what it lacks (jerseys, pants, socks, the Select Jerseys pictures) is the donor's (art/clubart.py)
DISC_ARTS = {87}
# their jersey colours (table NDEo, team = slot + 1: {(equipment, variant 1 home / 2 away): zones 1-9}; the pieces:
# custom_kit.PIECES): the community roster's, Coachella's black body and shoulders made this season's navy (equipment 9 zones 1
# and 5 since 0.31.0: round 34 painted equipment 1, the goalie's catching glove; lab round 37), the crest's colours
# (equipment 11 zones 1-3; 4-6 white, unused by the crests) and Coachella's socks (equipment 6) as the pack's kits. Played
# in lab round 34.
_NAVY, _TEAL, _ORANGE, _RED, _WHITE, _NONE = (0, 34, 63), (129, 229, 214), (180, 66, 18), (131, 13, 13), (255,) * 3, (0,) * 3
_GREY, _GOLD, _INK = (114, 114, 114), (180, 139, 18), (32, 32, 32)
_VEES_NAVY, _SKY = (12, 30, 65), (166, 210, 240)        # the Vees' crest
_JOK_RED, _JOK_YELLOW, _BLACK = (206, 17, 38), (252, 181, 20), (16, 16, 16)       # Jokerit's jester
_JUK_NAVY, _JUK_YELLOW = (0, 45, 98), (255, 205, 0)                                # Jukurit's crest
# and their two team colours (ttOk primary / secondary; the custom slots hold the placeholder blue / red, which goalie gear
# and the menus would take)
OWN_COLOURS = {234: (_NAVY, (200, 16, 46)), 235: ((27, 26, 27), (167, 168, 173)), VEES: (_VEES_NAVY, _SKY),
               JOKERIT: (_JOK_RED, _JOK_YELLOW), JUKURIT: (_JUK_NAVY, _JUK_YELLOW)}
# and their designs (ttOk, custom_kit.DESIGN_FIELDS): the community roster's. The game's own roster has 0 everywhere, and
# with jerseystyle 0 the game draws a custom team's jersey plain (white in lab round 46, black in the owner's RPCS3)
OWN_DESIGN = {slot: {'jerseystyle': 1, 'jerseybackhome': 0, 'jerseybackaway': 0, 'pantsstyle': 0, 'sockstyle': 1,
                     'font': 2} for slot in (234, 235, VEES, JOKERIT, JUKURIT)}
OWN_KIT = {
    234: {
        (1, 1): (_NAVY,) * 4 + (_TEAL,) + (_NAVY,) * 3 + (_ORANGE,),
        (2, 1): (_NAVY,) * 4 + (_TEAL,) + (_NAVY,) * 3 + (_ORANGE,),
        (3, 1): (_NAVY,) * 4 + (_TEAL, _RED, _NAVY, _ORANGE, _ORANGE),
        (4, 1): ((232, 232, 232), _INK, (18, 103, 140)) + (_NONE,) * 6,
        (5, 1): (_NAVY,) * 6 + (_TEAL, _NAVY, _NAVY),
        (6, 1): (_NAVY, (200, 16, 46), (242, 107, 33)) + (_NONE,) * 6,
        (7, 1): (_NAVY,) * 3 + (_NONE,) * 6,
        (8, 1): ((15, 15, 15), _NAVY, _WHITE) + (_NONE,) * 6,
        (9, 1): (_NAVY, _RED, _TEAL, _ORANGE, _NAVY, _TEAL) + (_NONE,) * 3,
        (10, 1): (_RED, _WHITE, _INK) + (_NONE,) * 6,
        (11, 1): (_NAVY, (200, 16, 46), (242, 107, 33)) + (_WHITE,) * 3 + (_NONE,) * 3,
        (1, 2): (_WHITE, _NAVY, _WHITE, _WHITE, _TEAL, _WHITE, _WHITE, _WHITE, _ORANGE),
        (2, 2): (_WHITE, _NAVY, _WHITE, _WHITE, _TEAL, _WHITE, _WHITE, _WHITE, _ORANGE),
        (3, 2): (_WHITE, _NAVY, _WHITE, _WHITE, _TEAL, _WHITE, _WHITE, _WHITE, _ORANGE),
        (4, 2): ((232, 232, 232), _INK, (18, 103, 140)) + (_NONE,) * 6,
        (5, 2): (_NAVY,) * 6 + (_TEAL, _NAVY, _NAVY),
        (6, 2): (_WHITE, _NAVY, (242, 107, 33)) + (_NONE,) * 6,
        (7, 2): (_NAVY,) * 3 + (_NONE,) * 6,
        (8, 2): (_WHITE, _WHITE, _ORANGE) + (_NONE,) * 6,
        (9, 2): (_WHITE, _TEAL, (7, 25, 34), _RED, _WHITE, (7, 25, 34)) + (_NONE,) * 3,
        (10, 2): ((7, 25, 34), _ORANGE, _WHITE) + (_NONE,) * 6,
        (11, 2): (_NAVY, (200, 16, 46), (242, 107, 33)) + (_WHITE,) * 3 + (_NONE,) * 3,
    },
    235: {
        (1, 1): (_GREY,) * 4 + (_GOLD,) + (_GREY,) * 3 + (_GOLD,),
        (2, 1): (_GREY,) * 4 + (_GOLD,) + (_GREY,) * 3 + (_GOLD,),
        (3, 1): (_GREY,) * 4 + (_GOLD, _GOLD, _GREY, _GOLD, _GOLD),
        (4, 1): ((233, 233, 233), _INK, (107, 27, 32)) + (_NONE,) * 6,
        (5, 1): (_INK, _GOLD, _INK, _INK, _INK, _INK, _GOLD, _INK, _INK),
        (6, 1): (_GREY, _INK, _GOLD) + (_NONE,) * 6,
        (7, 1): (_INK, _INK, (231, 231, 231)) + (_NONE,) * 6,
        (8, 1): ((204, 204, 204), _INK, _WHITE) + (_NONE,) * 6,
        (9, 1): (_GREY, _INK, _GOLD, _GREY, _GREY, _GOLD) + (_NONE,) * 3,
        (10, 1): (_WHITE, _GOLD, _GREY) + (_NONE,) * 6,
        (11, 1): ((27, 26, 27), (167, 168, 173), (245, 245, 245)) + (_WHITE,) * 3 + (_NONE,) * 3,
        (1, 2): (_WHITE,) * 4 + (_GOLD,) + (_WHITE,) * 3 + (_GREY,),
        (2, 2): (_WHITE,) * 4 + (_GOLD,) + (_WHITE,) * 3 + (_GREY,),
        (3, 2): (_WHITE, _GREY, _WHITE, _WHITE, _GOLD, _GREY, _WHITE, _GREY, _GREY),
        (4, 2): ((233, 233, 233), _INK, (107, 27, 32)) + (_NONE,) * 6,
        (5, 2): (_WHITE, _GOLD, _WHITE, _WHITE, _WHITE, _GOLD, _INK, _WHITE, _WHITE),
        (6, 2): (_WHITE, _GREY, _GOLD) + (_NONE,) * 6,
        (7, 2): (_INK, _INK, (231, 231, 231)) + (_NONE,) * 6,
        (8, 2): (_WHITE, _WHITE, _GREY) + (_NONE,) * 6,
        (9, 2): (_WHITE, _GREY, _GOLD, _GREY, _WHITE, _GOLD) + (_NONE,) * 3,
        (10, 2): (_GREY, _GOLD, _INK) + (_NONE,) * 6,
        (11, 2): ((27, 26, 27), (167, 168, 173), (245, 245, 245)) + (_WHITE,) * 3 + (_NONE,) * 3,
    },
    VEES: {
        (1, 1): (_VEES_NAVY,) * 4 + (_SKY,) + (_VEES_NAVY,) * 3 + (_WHITE,),
        (2, 1): (_VEES_NAVY,) * 4 + (_SKY,) + (_VEES_NAVY,) * 3 + (_WHITE,),
        (3, 1): (_VEES_NAVY,) * 4 + (_SKY, _WHITE, _VEES_NAVY, _WHITE, _WHITE),
        (4, 1): ((232, 232, 232), _INK, (18, 103, 140)) + (_NONE,) * 6,
        (5, 1): (_VEES_NAVY,) * 6 + (_SKY, _VEES_NAVY, _VEES_NAVY),
        (6, 1): (_VEES_NAVY, _SKY, _WHITE) + (_NONE,) * 6,
        (7, 1): (_VEES_NAVY,) * 3 + (_NONE,) * 6,
        (8, 1): (_VEES_NAVY, _VEES_NAVY, _WHITE) + (_NONE,) * 6,
        (9, 1): (_VEES_NAVY, _WHITE, _SKY, _WHITE, _VEES_NAVY, _SKY) + (_NONE,) * 3,
        (10, 1): (_WHITE, _SKY, _VEES_NAVY) + (_NONE,) * 6,
        (11, 1): (_VEES_NAVY, _SKY, _WHITE) + (_WHITE,) * 3 + (_NONE,) * 3,
        (1, 2): (_WHITE, _VEES_NAVY, _WHITE, _WHITE, _SKY, _WHITE, _WHITE, _WHITE, _VEES_NAVY),
        (2, 2): (_WHITE, _VEES_NAVY, _WHITE, _WHITE, _SKY, _WHITE, _WHITE, _WHITE, _VEES_NAVY),
        (3, 2): (_WHITE, _VEES_NAVY, _WHITE, _WHITE, _SKY, _WHITE, _WHITE, _WHITE, _VEES_NAVY),
        (4, 2): ((232, 232, 232), _INK, (18, 103, 140)) + (_NONE,) * 6,
        (5, 2): (_VEES_NAVY,) * 6 + (_SKY, _VEES_NAVY, _VEES_NAVY),
        (6, 2): (_WHITE, _VEES_NAVY, _SKY) + (_NONE,) * 6,
        (7, 2): (_VEES_NAVY,) * 3 + (_NONE,) * 6,
        (8, 2): (_WHITE, _WHITE, _VEES_NAVY) + (_NONE,) * 6,
        (9, 2): (_WHITE, _VEES_NAVY, _SKY, _VEES_NAVY, _WHITE, _SKY) + (_NONE,) * 3,
        (10, 2): (_VEES_NAVY, _SKY, _WHITE) + (_NONE,) * 6,
        (11, 2): (_VEES_NAVY, _SKY, _WHITE) + (_WHITE,) * 3 + (_NONE,) * 3,
    },
}


def _kit(main, trim, pants=None):
    """A kit in the Vees' pattern: dark at home (variant 1), white away (2), `pants` (default `main`) both ways."""
    pants, stick = pants or main, ((232, 232, 232), _INK, (18, 103, 140)) + (_NONE,) * 6
    return {(1, 1): (main,) * 4 + (trim,) + (main,) * 3 + (_WHITE,), (2, 1): (main,) * 4 + (trim,) + (main,) * 3 + (_WHITE,),
            (3, 1): (main,) * 4 + (trim, _WHITE, main, _WHITE, _WHITE), (4, 1): stick,
            (5, 1): (main,) * 6 + (trim, main, main), (6, 1): (main, trim, _WHITE) + (_NONE,) * 6,
            (7, 1): (pants,) * 3 + (_NONE,) * 6, (8, 1): (main, main, _WHITE) + (_NONE,) * 6,
            (9, 1): (main, _WHITE, trim, _WHITE, main, trim) + (_NONE,) * 3, (10, 1): (_WHITE, trim, main) + (_NONE,) * 6,
            (11, 1): (main, trim, _WHITE) + (_WHITE,) * 3 + (_NONE,) * 3,
            (1, 2): (_WHITE, main, _WHITE, _WHITE, trim, _WHITE, _WHITE, _WHITE, main),
            (2, 2): (_WHITE, main, _WHITE, _WHITE, trim, _WHITE, _WHITE, _WHITE, main),
            (3, 2): (_WHITE, main, _WHITE, _WHITE, trim, _WHITE, _WHITE, _WHITE, main), (4, 2): stick,
            (5, 2): (main,) * 6 + (trim, main, main), (6, 2): (_WHITE, main, trim) + (_NONE,) * 6,
            (7, 2): (pants,) * 3 + (_NONE,) * 6, (8, 2): (_WHITE, _WHITE, main) + (_NONE,) * 6,
            (9, 2): (_WHITE, main, trim, main, _WHITE, trim) + (_NONE,) * 3, (10, 2): (main, trim, _WHITE) + (_NONE,) * 6,
            (11, 2): (main, trim, _WHITE) + (_WHITE,) * 3 + (_NONE,) * 3}


OWN_KIT[JOKERIT] = _kit(_JOK_RED, _JOK_YELLOW, pants=_BLACK)
OWN_KIT[JUKURIT] = _kit(_JUK_NAVY, _JUK_YELLOW)


def listed(T, slot):
    """Does the unpatched game list this custom slot? Its team lists count the switched-on teams and walk ids 0, 1, 2 ...
    that far (0x12865c, 0x128348; lab round 41), so a team shows only when every slot before it is on. Each slot off on the
    way adds an empty "Custom Team N" (lab round 59). The patch's stage Y skips the slots that are off."""
    return all(T.get(t, 'NYKk') for t in range(slot))


def is_extra(T, slot):
    """Does the team table `T` hold its extra club (EXTRA_CLUBS) in `slot` (its club art id on a roster for the patched game,
    its create-a-team one otherwise), and not a team of the player's own?"""
    club = EXTRA_CLUBS.get(slot)
    return (bool(club and T.get(slot, 'NYKk')) and T.get(slot, 'RPbr') == club.code
            and T.get(slot, 'artid') in (OWN_ART[slot], CLUB_ART[slot]))


def is_vees(T):
    """Does the team table `T` hold the Penticton Vees in their slot?"""
    return is_extra(T, VEES)


def extras_in(T):
    """The slots of EXTRA_CLUBS that hold their club in the team table `T`."""
    return [slot for slot in sorted(EXTRA_CLUBS) if is_extra(T, slot)]


POS_CODE = {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}
POS_CLASS = {0: 'C', 1: 'W', 2: 'W', 3: 'D', 4: 'G'}
POS_NAME = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}
# cPbu.intlcountry codes (decoded from the players in the file)
NAT_CODE = {'SWE': 69, 'USA': 14, 'FIN': 67, 'CAN': 0, 'RUS': 76, 'NOR': 68, 'CZE': 82, 'CHE': 97, 'DEU': 85,
            'SVK': 95, 'BLR': 70, 'DNK': 66, 'AUT': 78, 'LVA': 74, 'FRA': 84, 'AUS': 98, 'JPN': 109, 'KAZ': 72,
            'UKR': 77, 'GBR': 83, 'POL': 91, 'ITA': 87, 'HUN': 86, 'SVN': 96, 'NLD': 89, 'LTU': 75, 'HRV': 81}
# national teams the original mod left empty, filled from the latest IIHF rosters
EMPTY_NATIONAL = {'AUT': 133, 'BLR': 134, 'GBR': 141, 'JPN': 143, 'KAZ': 144, 'NOR': 146, 'POL': 147, 'UKR': 152}
# how much weaker (rating-field units) than the mod's European national players an unrated player is
NATIONAL_TIER = {'AUT': 0, 'NOR': 0, 'BLR': 0, 'GBR': -2, 'KAZ': -2, 'POL': -3, 'UKR': -3, 'JPN': -3,
                 'DEU': 1, 'CHE': 1, 'SVK': 1, 'LVA': 0, 'DNK': 0, 'FRA': -1, 'ITA': -2}
# national team (ttOk abbreviation) -> birth country code used by the NHL data
NATIONAL_ISO = {'CAN': 'CAN', 'CZE': 'CZE', 'DEN': 'DNK', 'FIN': 'FIN', 'FRA': 'FRA', 'GER': 'DEU', 'ITA': 'ITA',
                'LAT': 'LVA', 'RUS': 'RUS', 'SLV': 'SVK', 'SWE': 'SWE', 'SWI': 'CHE', 'USA': 'USA',
                'AUS': 'AUT', 'BEL': 'BLR', 'GBR': 'GBR', 'JPN': 'JPN', 'KAZ': 'KAZ', 'NOR': 'NOR', 'POL': 'POL',
                'UKR': 'UKR'}

# NHL.com team codes by the full names other sources use
NHL_TEAM_NAMES = {
    'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF', 'Calgary Flames': 'CGY',
    'Carolina Hurricanes': 'CAR', 'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL',
    'Columbus Blue Jackets': 'CBJ', 'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM',
    'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJD', 'New York Islanders': 'NYI', 'New York Rangers': 'NYR',
    'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI', 'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS',
    'Seattle Kraken': 'SEA', 'St. Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
    'Utah Mammoth': 'UTA', 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK', 'Washington Capitals': 'WSH',
    'Winnipeg Jets': 'WPG'}


def team_code(name):
    """NHL.com code for a team given as a code or a full name (None when unknown)."""
    if name in API_TO_SLOT:
        return name
    return NHL_TEAM_NAMES.get(name)


# country codes as leagues and the IOC write them, where they differ from the ISO codes above
COUNTRY_ALIASES = {'GER': 'DEU', 'SUI': 'CHE', 'DEN': 'DNK', 'LAT': 'LVA', 'SLO': 'SVN', 'NED': 'NLD',
                   'CRO': 'HRV', 'ENG': 'GBR'}


def country_code(code):
    """cPbu.intlcountry value for an ISO or IOC country code (None when the game's code is not known)."""
    if not code:
        return None
    code = code.upper()
    return NAT_CODE.get(COUNTRY_ALIASES.get(code, code))
# born abroad but represent another country -- never picked for their birth country's team
NOT_ELIGIBLE = {('mason', 'mctavish'), ('benoitolivier', 'groulx')}


def city_key(text):
    """A custom team's city as a key in the game's own style: 'Coachella Valley' -> COACHELLA_VALLEY.

    A custom team's name in the menus is the game's text whose key is its `shortname` (art/loc.py).
    The keys that show are written like the game's own (ANAHEIM, LAS_VEGAS); the community's
    "NhlCityName_13" and the texts this program added under "Coachella Valley" or
    "2026 Prospects 2" showed nothing in the game (owner, 2026-10-04)."""
    plain = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z0-9]+', '_', plain.upper()).strip('_')


def is_city_key(text):
    return bool(re.fullmatch(r'[A-Z0-9_]+', text or ''))


def set_city(T, slot, city):
    """Write a team's city (`shortname`); a custom team's as a key in the game's style."""
    if T.get(slot, 'league') == CUSTOM_LEAGUE and not is_city_key(city):
        city = city_key(city) or city
    T.set(slot, 'shortname', city[:T.field('shortname').bits // 8 - 1])


class LayoutError(ValueError):
    """The roster is not one the updater can work on."""


# the layouts the updater works on (check_base): the community roster family, and the game's own
# roster (stock.py: from the player's disc, or saved in the game without loading a community roster)
COMMUNITY, STOCK = 'community', 'stock'


def mirrors(kind):
    """The custom copies of NHL teams a layout keeps in step: none in the game's own roster."""
    return MIRRORS if kind == COMMUNITY else {}


def copies(R):
    """{copy slot: its NHL team} of the custom copies `R`'s own layout keeps (mirrors): none on the game's own roster,
    where slots 222-233 may hold clubs of the player's own (a tester's KHL clubs); a roster of no known layout is
    taken as the community's."""
    try:
        kind = check_base(R)
    except LayoutError:
        kind = COMMUNITY
    return {m: p for p, ms in mirrors(kind).items() for m in ms}


def team_leagues(R):
    return [R.T.get(t, 'jjMx') for t in range(R.T.cur_rec)]


def check_base(R):
    """The layout of `R` (COMMUNITY or STOCK); LayoutError when the updater cannot work on it.

    Two layouts are known: the community roster family, and the game's own roster (30 NHL teams
    and the All-Star teams, the custom teams switched off; stock.py prepares it). Anything else,
    and a different table set, is rejected with a message a player can act on. The custom copies
    of NHL teams of a community roster may be out of step with their team (the update makes them
    copies again): they are recognised by their name or by sharing most players with it."""
    from . import stock
    T, U = R.T, R.U
    if T.cur_rec != TEAM_COUNT:
        raise LayoutError(f"this roster has {T.cur_rec} teams; the updater needs the 252-team NHL Legacy layout")
    count = Counter(U.get(i, 'BSXd') for i in range(U.cur_rec))
    if any(count[t] > MAX_PER_TEAM for t in count):
        raise LayoutError("a team has more than 40 players")
    if stock.is_stock(R):
        return STOCK
    if not all(count[m] for m in MIRROR_OF) or not T.get(222, 'NYKk'):
        raise LayoutError(
            "some of the custom copies of NHL teams are missing, so this is neither the game's own roster nor a "
            "community roster. Pick another roster, or start from the game's own roster.")
    members = {}
    for i in range(U.cur_rec):
        members.setdefault(U.get(i, 'BSXd'), set()).add(R.link_to_pid.get(U.get(i, 'TWSX')))
    for prim, mirrors in MIRRORS.items():
        for m in mirrors:
            if R.team_name(m).replace('®', '').strip() == MIRROR_NAMES[m]:
                continue
            a, b = members.get(prim, set()), members.get(m, set())
            if len(a & b) < 0.6 * max(len(a), len(b), 1):
                raise LayoutError(
                    f"{R.team_name(m)} (team {m}) is not a copy of {R.team_name(prim)} in this roster; "
                    "the team layout differs from the community roster.")
    return COMMUNITY

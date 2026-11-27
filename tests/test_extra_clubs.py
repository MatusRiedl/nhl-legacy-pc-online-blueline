"""Jokerit and Jukurit in custom slots 249 / 250 (layout.EXTRA_CLUBS): in the Liiga with art ids 87 (Jokerit's own, on the
disc) and 903 on a roster for the patched game, custom teams without the patch where the game's lists can reach them
(owner, 2026-11-26, a tester's ask; docs/notes/liiga-jokerit-jukurit.md). The Vees' recipe (tests/test_vees.py)."""
import os

import pytest

from legacy_roster import gamepatch, pipeline, schedule, stock, verify
from legacy_roster import layout as L
from legacy_roster.builder import Data
from legacy_roster.leagues import pools
from legacy_roster.matching import norm
from legacy_roster.roster import Roster

CLUBS = {L.JOKERIT: ('Jokerit', 'JOK', 87, 'Veikkaus Arena'), L.JUKURIT: ('Jukurit', 'JUK', 903, "Let's Go Areena")}


def members(R, team):
    return [R.p_by_id[R.link_to_pid[R.U.get(e, 'playerindex')]] for e in range(R.U.cur_rec) if R.U.get(e, 'team') == team]


def liiga(pack):
    return Data(season_year=pack['season'], leagues={'liiga': pack['leagues']['liiga']})


def patched_data(pack):
    return Data(season_year=pack['season'], leagues={'liiga': pack['leagues']['liiga']}, schedule=pack['schedule'],
                calendar=schedule.ALL_PATCH)


@pytest.fixture(scope='module')
def built(base_bytes, pack):
    res = pipeline.build(base_bytes, liiga(pack), steps=['liiga'])
    assert res.problems == []
    return res


@pytest.fixture(scope='module')
def patched(base_bytes, pack):
    """A roster for the patched game with Jokerit and Jukurit."""
    res = pipeline.build(base_bytes, patched_data(pack), steps=['liiga', pipeline.SCHEDULE], game_patch=True)
    out, problems, _ = pipeline.patch_roster(res, base_bytes, pack, pack['season'])
    assert problems == []
    return out


def test_the_table_keeps_the_vees_as_they_were():
    assert L.EXTRA_CLUBS[L.VEES].code == 'PEN' and L.CLUB_ART[L.VEES] == 902 and L.OWN_ART[L.VEES] == 20085
    assert (L.JOKERIT, L.JUKURIT) == (249, 250) and L.DISC_ARTS == {87}
    assert len(set(L.OWN_ART.values())) == len(L.OWN_ART) and len(set(L.CLUB_ART.values())) == len(L.CLUB_ART)
    assert 20054 not in L.OWN_ART.values()                  # create-a-team logo 54: never (custom_kit.free_logo)
    assert set(gamepatch.LEAGUE_SLOTS) == {234, 235, 249, 250, 251}
    assert gamepatch.LEAGUE_SLOTS[L.JOKERIT] == gamepatch.LEAGUE_SLOTS[L.JUKURIT] == gamepatch.LIIGA


def test_they_get_slots_249_and_250_on_every_roster(built, pack):
    R = Roster(built.data)
    T = R.T
    extra = {c['art']: c for c in pack['leagues']['liiga']['extra']}
    for slot, (name, code, _art, _arena) in CLUBS.items():
        assert L.is_extra(T, slot) and slot in L.extras_in(T)
        assert T.get(slot, 'JkmY') == name and T.get(slot, 'RPbr') == code and T.get(slot, 'nnsx') == code
        assert T.get(slot, 'artid') == L.OWN_ART[slot] and T.get(slot, 'league') == L.CUSTOM_LEAGUE
        names = {(norm(R.P.get(r, 'firstname')), norm(R.P.get(r, 'lastname'))) for r in members(R, slot)}
        assert len(names & {(norm(p['first']), norm(p['last'])) for p in extra[code]['players']}) >= 20, name
        assert len(members(R, slot)) <= L.MAX_PER_TEAM
        assert not any(name in str(row[2]) and 'No slot' in str(row[2]) for row in built.log)
    assert L.is_vees(T) is False                            # the Liiga step alone leaves the Vees' slot alone


def test_their_arenas_are_their_own_when_the_table_has_room(built):
    R = Roster(built.data)
    A = R.f['OEtS']
    for slot, (_name, _code, _art, arena) in CLUBS.items():
        row = R.T.get(slot, 'arenaid')
        assert A.get(row, 'arenaname') == arena
        assert not [t for t in range(R.T.cur_rec) if t != slot and R.T.get(t, 'arenaid') == row]


def test_a_second_run_changes_nothing(built, pack):
    res = pipeline.build(built.data, liiga(pack), steps=['liiga'])
    assert res.problems == [] and res.data == built.data


def test_the_update_tab_does_not_call_them_left_out(pack):
    assert {'Jokerit', 'Jukurit'} <= set(pack['leagues']['liiga']['left_out'])
    note = pipeline.left_out_note(pack, 'liiga') or ''
    assert 'Jokerit' not in note and 'Jukurit' not in note


def test_their_names_are_written(built):
    names = pipeline.names_of(built.data)
    assert names['cities']['JOKERIT'] == 'Jokerit' and names['cities']['JUKURIT'] == 'Jukurit'
    assert ('JOK', 'Jokerit', 'Jokerit', 'Jokerit', 'JOK') in names['teams']
    assert ('JUK', 'Jukurit', 'Jukurit', 'Jukurit', 'JUK') in names['teams']


def test_jokerit_wears_the_disc_s_own_logo(built):
    """The tester: "some of their old stuff should be in the game" (art 87's jester)."""
    assert L.EXTRA_CLUBS[L.JOKERIT].logo == 'disc:87' and L.EXTRA_CLUBS[L.JUKURIT].logo is None


def test_they_are_listed_once_every_slot_before_them_is_on(built):
    T = Roster(built.data).T
    assert not L.listed(T, L.JOKERIT)       # the Liiga alone leaves the prospect pools' slots off; the list of changes says so
    assert any(row[2] == 'Jokerit' and 'team list' in str(row[3]) for row in built.log)


def test_their_players_get_liiga_starter_deals():
    from legacy_roster import contracts
    assert contracts.starter_league(L.JOKERIT) == contracts.starter_league(L.JUKURIT) == contracts.starter_league(80)
    assert contracts.starter_league(L.VEES) == 'CHL'


@pytest.fixture(scope='module')
def stock_bytes():
    disc = os.environ.get('LEGACY_ROSTER_DISC')
    if not disc or not os.path.exists(disc):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    return stock.from_disc(disc)


def test_the_game_s_own_roster_has_neither_for_the_unpatched_game(stock_bytes, pack):
    T = Roster(pipeline.build(stock_bytes, liiga(pack), steps=['liiga']).data).T
    assert not T.get(L.JOKERIT, 'NYKk') and not T.get(L.JUKURIT, 'NYKk')


def test_the_game_s_own_roster_has_both_for_the_patched_game(stock_bytes, pack):
    res = pipeline.build(stock_bytes, liiga(pack), steps=['liiga'], game_patch=True)
    assert res.problems == []
    R = Roster(res.data)
    for slot in CLUBS:
        assert L.is_extra(R.T, slot) and len(members(R, slot)) >= 20


def test_a_players_own_team_in_their_slot_stays(base_bytes, pack):
    R = Roster(base_bytes)
    R.T.set(L.JOKERIT, 'NYKk', 1)
    R.T.set(L.JOKERIT, 'JkmY', 'Bratislava Dragons')
    res = pipeline.build(R.f.build(), liiga(pack), steps=['liiga'])
    after = Roster(res.data)
    assert res.problems == [] and after.T.get(L.JOKERIT, 'JkmY') == 'Bratislava Dragons' and not members(after, L.JOKERIT)
    assert not L.is_extra(after.T, L.JOKERIT) and L.is_extra(after.T, L.JUKURIT)


def test_a_players_own_team_named_after_jokerit_keeps_the_club(base_bytes, pack):
    R = Roster(base_bytes)
    R.T.set(240, 'NYKk', 1)
    R.T.set(240, 'JkmY', 'Helsinki Jokerit')
    res = pipeline.build(R.f.build(), liiga(pack), steps=['liiga'])
    after = Roster(res.data)
    assert res.problems == [] and len(members(after, 240)) >= 20
    assert after.T.get(240, 'JkmY') == 'Helsinki Jokerit'
    assert not after.T.get(L.JOKERIT, 'NYKk') and L.is_extra(after.T, L.JUKURIT)


def test_a_prospect_pool_in_their_slot_moves_out(base_bytes, pack):
    """A full update of 0.99.1 or older fills all 16 spare slots with prospect pools, 249 and 250 among them."""
    R = Roster(base_bytes)
    R.T.set(L.JOKERIT, 'NYKk', 1)
    for field, value in (('JkmY', 'Panthers System'), ('RPbr', 'FLAS'), ('nnsx', 'FLAS')):
        R.T.set(L.JOKERIT, field, value)
    pool = next(t for t in L.EUROPE if pools.is_pool(R, t))
    prospects = [e for e in range(R.U.cur_rec) if R.U.get(e, 'team') == pool][:6]
    pids = {R.link_to_pid[R.U.get(e, 'playerindex')] for e in prospects}
    for e in prospects:
        R.U.set(e, 'team', L.JOKERIT)
    res = pipeline.build(R.f.build(), liiga(pack), steps=['liiga'])
    after = Roster(res.data)
    assert res.problems == [] and L.is_extra(after.T, L.JOKERIT) and after.T.get(L.JOKERIT, 'JkmY') == 'Jokerit'
    moved = {after.link_to_pid[after.U.get(e, 'playerindex')]: after.U.get(e, 'team') for e in range(after.U.cur_rec)
             if after.link_to_pid[after.U.get(e, 'playerindex')] in pids}
    assert moved and L.JOKERIT not in moved.values()
    again = pipeline.build(res.data, liiga(pack), steps=['liiga'])
    assert again.problems == [] and again.data == res.data


def test_a_roster_updated_before_they_came_gets_their_real_players(base_bytes, data, pack):
    """Lab round 66 (2026-11-27): a full update of 0.99.1 leaves no spare player record and prospect pools in 249 / 250.
    Updated in place, Jokerit and Jukurit got 7 of their players: 51 were skipped ("no free player record left") and pool
    prospects stayed to fill the line-up. Their players now make room as an NHL newcomer does (Builder.make_room)."""
    steps = pipeline.steps_for(pack)
    liiga_old = dict(pack['leagues']['liiga'], extra=[c for c in pack['leagues']['liiga']['extra']
                                                      if c.get('art') not in ('JOK', 'JUK')])

    def with_leagues(leagues):
        return Data(nhl_players=data.nhl_players, ratings_list=data.ratings_list, iihf=data.iihf,
                    season_year=data.season_year, leagues=leagues, drafts=pack.get('drafts'), contracts=data.contracts)
    before = pipeline.build(base_bytes, with_leagues(dict(pack['leagues'], liiga=liiga_old)), steps=steps)
    assert before.problems == []
    old = Roster(before.data)
    assert not L.is_extra(old.T, L.JOKERIT) and pools.is_pool(old, L.JOKERIT) and pools.is_pool(old, L.JUKURIT)
    full = with_leagues(pack['leagues'])
    after = pipeline.build(before.data, full, steps=steps)
    assert after.problems == []
    R = Roster(after.data)
    extra = {c['art']: c for c in pack['leagues']['liiga']['extra']}
    for slot, (name, code, _art, _arena) in CLUBS.items():
        listed = {(norm(p['first']), norm(p['last'])) for p in extra[code]['players']}
        names = {(norm(R.P.get(r, 'firstname')), norm(R.P.get(r, 'lastname'))) for r in members(R, slot)}
        assert L.is_extra(R.T, slot) and len(names & listed) >= len(listed) - 2, name
        assert not [r for r in after.log if r[0] == code and r[1] in ('skipped', 'stays to fill the line-up')], name
    third = pipeline.build(after.data, full, steps=steps)
    assert third.problems == [] and third.data == after.data


def test_without_the_liiga_step_the_slots_stay_as_they_were(base_bytes, pack):
    res = pipeline.build(base_bytes, Data(season_year=pack['season'], leagues={'shl': pack['leagues']['shl']}), steps=['shl'])
    T = Roster(res.data).T
    assert not T.get(L.JOKERIT, 'NYKk') and not T.get(L.JUKURIT, 'NYKk')


def test_on_a_patch_roster_they_are_liiga_clubs_with_art_87_and_903(patched):
    R = Roster(patched)
    for slot, (_name, _code, art, _arena) in CLUBS.items():
        assert gamepatch.league_of(R, slot) == gamepatch.LIIGA == gamepatch.league_of(R, 80)
        assert R.T.get(slot, 'artid') == art and R.T.get(slot, gamepatch.CREATED) == 0 and L.is_extra(R.T, slot)
        assert sorted(row['TccF'] for row in gamepatch.own_rows(R, slot)) == sorted(L.CLUB_DONOR[slot][1])
        assert {row[gamepatch.ROW_TEAM] for row in gamepatch.art_rows(R, art)} == {slot}
    assert gamepatch.check_league_fit(R) == [] and gamepatch.check_art_fit(R) == []
    assert [t for t in range(R.T.cur_rec) if R.T.get(t, 'artid') == 87] == [L.JOKERIT]


def test_reading_a_patch_roster_puts_them_back_as_the_builder_knows_them(patched):
    R = Roster(patched)
    gamepatch.unleague(R)
    gamepatch.unart(R)
    for slot, (_name, _code, art, _arena) in CLUBS.items():
        assert gamepatch.league_of(R, slot) == gamepatch.CUSTOM_GROUPS
        assert R.T.get(slot, 'artid') == L.OWN_ART[slot] and R.T.get(slot, gamepatch.CREATED) == 1
        assert gamepatch.art_rows(R, art) == [] and L.is_extra(R.T, slot)


def test_unpatching_their_roster_turns_them_back_into_custom_teams(patched, pack, stock_bytes):
    res = pipeline.build(patched, liiga(pack), steps=['liiga'], normal_from=Roster(stock_bytes))
    assert res.problems == []
    R = Roster(res.data)
    for slot, (_name, _code, art, _arena) in CLUBS.items():
        assert gamepatch.league_of(R, slot) == gamepatch.CUSTOM_GROUPS and R.T.get(slot, 'artid') == L.OWN_ART[slot]
        assert gamepatch.art_rows(R, art) == [] and L.is_extra(R.T, slot) and len(members(R, slot)) >= 20


def test_slots_249_and_250_of_someone_else_are_left_alone_by_the_patch(base_bytes):
    R = Roster(base_bytes)
    for slot in CLUBS:
        R.T.set(slot, 'NYKk', 1)
        R.T.set(slot, 'JkmY', 'Bratislava Dragons')
    gamepatch.league_fit(R)
    gamepatch.art_fit(R)
    for slot, (_name, _code, art, _arena) in CLUBS.items():
        assert gamepatch.league_of(R, slot) == gamepatch.CUSTOM_GROUPS and R.T.get(slot, 'artid') != art
    assert gamepatch.check_league_fit(R) == [] and gamepatch.check_art_fit(R) == []


def test_unart_leaves_art_87_of_another_team_alone(base_bytes):
    """87 is the disc's own art: a player's own Jokerit on another slot keeps it and its rows."""
    R = Roster(base_bytes)
    R.T.set(240, 'NYKk', 1)
    R.T.set(240, 'artid', 87)
    W = R.f['wgjx']
    W.add_record(dict(gamepatch.art_rows(R, 86)[0], **{gamepatch.ROW_ART: 87, gamepatch.ROW_TEAM: 240}))
    gamepatch.unart(R)
    assert R.T.get(240, 'artid') == 87 and len(gamepatch.art_rows(R, 87)) == 1


def test_verify_allows_the_liiga_fields_only_on_their_slots_and_only_patched(patched, base_bytes):
    src = Roster(base_bytes)
    assert not [p for p in verify.verify(patched, src, farm_patch=True)[0] if 'changed league' in p or 'art id' in p]
    unpatched = [p for p in verify.verify(patched, src)[0] if 'changed league' in p or 'art id' in p]
    assert len([p for p in unpatched if 'changed league' in p]) >= 2 and any('87' in p for p in unpatched)
    R = Roster(base_bytes)
    R.T.set(248, 'NYKk', 1)
    for field, value in zip(gamepatch.LEAGUE_FIELDS, gamepatch.LIIGA):
        R.T.set(248, field, value)
    R.T.set(247, 'artid', 87)
    problems = verify.verify(R.f.build(), src, farm_patch=True)[0]
    assert any('changed league' in p for p in problems) and any('art id 87' in p for p in problems)


def test_verify_does_not_blame_art_87_the_source_already_had(base_bytes):
    R = Roster(base_bytes)
    R.T.set(240, 'NYKk', 1)
    R.T.set(240, 'artid', 87)
    data = R.f.build()
    assert not any('art id 87' in p for p in verify.verify(data, Roster(data))[0])


# --- their look ---------------------------------------------------------------------------------------------------------
def test_the_clubs_logos_reach_their_slots_also_when_the_liiga_did_not_run_now(patched, built, pack):
    from legacy_roster.art import looks
    for data in (patched, built.data):
        links = looks.club_logos(Roster(data), pack['leagues'])
        assert links[L.JOKERIT] == 'disc:87'
        jukurit = next(c for c in pack['leagues']['liiga']['extra'] if c['art'] == 'JUK').get('logo')
        assert links.get(L.JUKURIT) == jukurit
    assert looks.club_logos(Roster(built.data), {})[L.JOKERIT] == 'disc:87'    # the data pack's Liiga is not needed for it


def test_on_the_patched_game_jokerit_keeps_its_old_centre_ice_and_both_get_jerseys_from_their_colours(patched, monkeypatch):
    from PIL import Image
    from legacy_roster.art import looks
    crest = Image.new('RGBA', (64, 64), (200, 16, 46, 255))
    monkeypatch.setattr(looks, '_logos', lambda link, pack, cache: (crest, crest))
    R = Roster(patched)
    made = {look.art: look for look in looks.looks_from(R, {}, {L.JOKERIT: 'disc:87', L.JUKURIT: 'crest:j'}, {})}
    assert made[87].centre != 'make' and made[903].centre == 'make'
    assert [v for v, _light in made[87].versions] == list(L.CLUB_DONOR[L.JOKERIT][1])
    assert [v for v, _light in made[903].versions] == list(L.CLUB_DONOR[L.JUKURIT][1])
    assert looks.CENTRE.format(a=87) not in looks.look_paths(made[87])


# --- the window ---------------------------------------------------------------------------------------------------------
def test_the_calendar_tab_shows_their_64_real_games_each(built, pack):
    from legacy_roster.app.calendar import EXTRA_NOTE, VEES_NOTE
    from .test_calendar_office import Editor, tabs
    ed = Editor(built.data)
    ed.update = type('Update', (), {'pack': pack})()
    cal, _office, _host = tabs(ed)
    rail = cal.rail_numbers()
    for slot in CLUBS:
        cal.follow(slot)
        s = cal.snapshot()
        assert s['league'] == 'Liiga' and s['summary']['gp'] == 64 and s['summary']['home'] == 32, slot
        assert s['league_note'] != VEES_NOTE and s['league_note'].endswith("plays the other 15 clubs.")
        assert rail[slot]['text'] == '64'
    cal.follow(L.JOKERIT)
    assert cal.snapshot()['league_note'] == EXTRA_NOTE.format(name=cal.snapshot()['team']['name'], league='Liiga', n=15)
    derby = [g for g in pack['schedules']['liiga'] if {g[1], g[2]} == {'Jokerit', 'Jukurit'}]
    assert derby                                    # their games against each other show for both, once
    cal.day(derby[0][0])
    day = cal.snapshot()['day']
    assert sum(1 for g in day['games'] if {g['home']['id'], g['away']['id']} == {L.JOKERIT, L.JUKURIT}) == 1
    cal.follow(min(L.LIIGA))                        # the other clubs' lists stay the roster's table
    assert not any(g['vs'] in ('JOK', 'JUK') for m in cal.snapshot()['months'] for g in m['games'])


def test_the_team_list_shows_them_under_the_liiga(built, patched):
    from legacy_roster.editor.model import Snapshot
    for data in (built.data, patched):
        snap = Snapshot(Roster(data))
        assert snap.team_league[L.JOKERIT] == snap.team_league[L.JUKURIT] == 'Liiga'

import logging
from flask import Flask, jsonify, render_template, request

from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

import time
import sys

from pokedex import pokedex
from inventory import items

app = Flask(__name__)

BASE_PATH = ''

API_PATH = '/api/1'

sessions = {}
users = []

def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('Line %(lineno)d,%(filename)s - %(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def encounterAndCatch(session, pokemon, thresholdP=0.5, limit=5, delay=2):
    # Start encounter
    encounter = session.encounterPokemon(pokemon)

    # Grab needed data from proto
    chances = encounter.capture_probability.capture_probability
    balls = encounter.capture_probability.pokeball_type
    bag = session.checkInventory().bag

    # Have we used a razz berry yet?
    berried = False

    # Make sure we aren't oer limit
    count = 0

    # Attempt catch
    while True:
        bestBall = 2
        RAZZ_BERRY = 701

        # Check for balls and see if we pass
        # wanted threshold
        for i in range(len(balls)):
            if balls[i] in bag and bag[balls[i]] > 0:
                if chances[i] > thresholdP:
                    bestBall = balls[i]
                    break

        if not berried and RAZZ_BERRY in bag and bag[RAZZ_BERRY]:
            logging.info("Using a RAZZ_BERRY")
            session.useItemCapture(RAZZ_BERRY, pokemon)
            berried = True
            time.sleep(delay)
            continue

        # Try to catch it!!
        logging.info("Using a %s" % items[bestBall])
        attempt = session.catchPokemon(pokemon, bestBall)
        time.sleep(delay)

        # Success or run away
        if attempt.status == 1:
            return attempt

        # CATCH_FLEE is bad news
        if attempt.status == 3:
            logging.info("Possible soft ban.")
            return attempt

        # Only try up to x attempts
        count += 1
        if count >= limit:
            logging.info("Over catch limit")
            return None


# Catch a pokemon at a given point
def walkAndCatch(session, pokemon):
    if pokemon:
        logging.info("Catching %s:" % pokedex[pokemon.pokemon_data.pokemon_id])
        session.walkTo(pokemon.latitude, pokemon.longitude, step=2.8)
        enc = encounterAndCatch(session, pokemon)
        logging.info(enc)

def parseResponseResult(result, operation=''):
    """
    result: SUCCESS candy_awarded: 1
    """

    body = {}
    body['result'] = getattr(result, "result", None)

    if body['result'] == 'SUCCESS':
        if operation == 'FREE_POKEMON':
            body['candy_awarded'] = getattr(result, "candy_awarded", None)

    return body

def parseWildPokemon(pokemon):
    #logging.info(str(pokemon))
    pok = {}

    pokemonId = getattr(pokemon, "pokemon_id", None)
    if not pokemonId:
        pokemonId = pokemon.pokemon_data.pokemon_id
    pok['pokemon_id'] = pokemonId
    pok['rarity'] = pokedex.getRarityById(pokemonId)
    pok['name'] = pokedex[pokemonId]
    pok['encounter_id'] = getattr(pokemon, "encounter_id", None)
    pok['last_modified_timestamp_ms'] = getattr(pokemon, "last_modified_timestamp_ms", None)
    pok['latitude'] = getattr(pokemon, "latitude", None)
    pok['longitude'] = getattr(pokemon, "longitude", None)
    pok['spawn_point_id'] = getattr(pokemon, "spawn_point_id", None)
    pok['time_till_hidden_ms'] = getattr(pokemon, "time_till_hidden_ms", None)

    return pok

def parsePartyPokemon(pokemon, detail=False):
    """
    id: 17633600020994617271 
    pokemon_id: TENTACOOL 
    cp: 224 
    stamina: 35 
    stamina_max: 35 
    move_1: BUBBLE_FAST 
    move_2: WRAP 
    height_m: 0.742571890354 
    weight_kg: 33.6002044678 
    individual_attack: 11 
    individual_defense: 2 
    individual_stamina: 4 
    cp_multiplier: 0.422500014305 
    pokeball: ITEM_GREAT_BALL 
    captured_cell_id: 5171193400942133248 
    creation_time_ms: 1469649774858
    """

    short = ['id','stamina_max','cp','cp_multiplier','individual_attack','individual_defense','individual_stamina']
    full = ['stamina','move_1','move_2','height_m','weight_kg',
        'pokeball','captured_cell_id','creation_time_ms']
    props = []

    #logging.info(str(pokemon))
    pok = {}

    pokemonId = getattr(pokemon, "pokemon_id", None)

    pok['pokemon_id'] = pokemonId
    pok['rarity'] = pokedex.getRarityById(pokemonId)
    pok['name'] = pokedex[pokemonId]

    if detail:
        props = short + full
    else:
        props = short
    
    for value in props:
        pok[value] = getattr(pokemon, value, None)

    return pok

def parseEggs(egg):
    """
    egg free:
    id: 4555645718830338274
    is_egg: true
    egg_km_walked_target: 5.0
    captured_cell_id: 5171192829494427648
    creation_time_ms: 1469698248933

    egg ocup:
    id: 4555645718830338274
    is_egg: true
    egg_km_walked_target: 5.0
    captured_cell_id: 5171192829494427648
    egg_incubator_id: "EggIncubatorProto4824214944684084552"
    creation_time_ms: 1469698248933
    """
    parsed_egg = {}

    parsed_egg['id'] = getattr(egg, "id", None)
    parsed_egg['egg_km_walked_target'] = getattr(egg, "egg_km_walked_target", None)
    parsed_egg['captured_cell_id'] = getattr(egg, "captured_cell_id", None)
    parsed_egg['is_egg'] = getattr(egg, "is_egg", None)
    parsed_egg['egg_incubator_id'] = getattr(egg, "egg_incubator_id", None)
    parsed_egg['creation_time_ms'] = getattr(egg, "creation_time_ms", None)

    return parsed_egg

def parseProfile(profile):
    """
    success: true 
    player_data { 
        creation_timestamp_ms: 1467992781323 
        username: "jm8nav" 
        team: BLUE 
        tutorial_state: LEGAL_SCREEN 
        tutorial_state: AVATAR_SELECTION 
        tutorial_state: POKEMON_CAPTURE 
        tutorial_state: NAME_SELECTION 
        tutorial_state: FIRST_TIME_EXPERIENCE_COMPLETE 
        avatar { 
            skin: 1 
            hair: 3 
            shirt: 2 
            pants: 1 
            hat: 2 
            shoes: 2 
            eyes: 3 
            backpack: 2 
        } 
        max_pokemon_storage: 250 
        max_item_storage: 350 
        daily_bonus { 
            next_defender_bonus_collect_timestamp_ms: 1469541558462 
        } 
        equipped_badge { } 
        contact_settings { 
            send_marketing_emails: true 
        } 
        currencies { 
            name: "POKECOIN" 
            amount: 20 
        } 
        currencies { 
            name: "STARDUST" 
            amount: 29966 
        } 
    }
    """
    body = {}
    fields = ['creation_timestamp_ms','username','team','max_pokemon_storage','max_item_storage']
    logging.info(getattr(profile, "success", None))
    if getattr(profile, "success", False) == True:
        player_data = getattr(profile, 'player_data', None)
        for field in fields:
            body[field] = getattr(player_data, field, None)

        #avatar_data = getattr(player_data, 'avatar', None)
        #avatar = {}
        #for prop in avatar_data:
        #    avatar[prop] = avatar_data[prop]
        #body['avatar'] = avatar
        currencies = getattr(player_data, 'currencies', None)
        for currency in currencies:
            body[currency.name.lower()] = currency.amount

    return body

@app.route(BASE_PATH + "/")
def home():
    """Render website's home page."""
    return render_template('home.html')

@app.route(API_PATH + "/")
def index():
    """Render website's home page."""
    return str(users)

@app.route(BASE_PATH + "/login", methods=['POST'])
def login_data():
    if request.json:
        mydata = request.json
        username = mydata.get("username")
        password = mydata.get("password")
        auth = mydata.get("auth")
        location = mydata.get("location")

        if username == None or password == None or auth == None or location == None:
            return jsonify(error="missing value"), 400

        poko_session = PokeAuthSession(
            username,
            password,
            auth,
            geo_key=None
        )

        session = poko_session.authenticate(locationLookup=location)

        if session:
            global sessions
            global users
            sessions[username] = session
            users.append(username)
            logging.info(users)

            return jsonify(data=str(session))
        else:
            return jsonify(error=str(session)), 400

    else:
        return jsonify(error="no values receives"), 400

@app.route(BASE_PATH + "/login/<auth_type>/<user>/<password>/<location>")
def login(auth_type, user, password, location):
    """
    Access Token: eyJhbGciOiJSUzI1NiIsImtpZCI6ImE5NzAyMjQ0YWE3YjMyYT
        BjZjM4MWNjNjVhZDk4OGYyMzllYmIzOWYifQ.eyJpc3MiOiJhY2NvdW50cy5
        nb29nbGUuY29tIiwiYXVkIjoiODQ4MjMyNTExMjQwLTdzbzQyMWpvdHIyNjA
        5cm1xYWtjZXV1MWx1dXEwcHRiLmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29
        tIiwic3ViIjoiMTExNjc4NjkwMjc5NTg4MzQ5MTIxIiwiZW1haWxfdmVyaWZ
        pZWQiOnRydWUsImF6cCI6Ijg0ODIzMjUxMTI0MC0zdmRydHJmZG50bGpmMnU
        0bWxndG5ubGhuaWduMzVkNS5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSI
        sImVtYWlsIjoiam04bmF2QGdtYWlsLmNvbSIsImlhdCI6MTQ2OTcwODM2NCw
        iZXhwIjoxNDY5NzExOTY0LCJuYW1lIjoiSm9zZSBNaWd1ZWwgTmF2YXJybyB
        JZ2xlc2lhcyIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29
        udGVudC5jb20vLVh1Zzk3b2F2TXljL0FBQUFBQUFBQUFJL0FBQUFBQUFBVTh
        ZL2lkc0VneDBkU0tFL3M5Ni1jL3Bob3RvLmpwZyIsImdpdmVuX25hbWUiOiJ
        Kb3NlIE1pZ3VlbCIsImZhbWlseV9uYW1lIjoiTmF2YXJybyBJZ2xlc2lhcyJ
        9.i4ku4mRx2u1qKkfE7bZRRd2UZpywFRLwJkTSHhNIPpNSqLoICWhY8ULeIJ
        chCmBfWlunyKbFhOGKEy3tnByReR5WxbIv5BVhh5W5Jo75kCScr-nfMlXDew
        Kq3WzwQNxwHk-5bOIpFFtGRdtmsmPEB4zHZPbTHxh44metWY5LgYsMF9eeDY
        OHyLkb3hxyZEjYlnKm4Sz9lutpgun61ZujPdHpN-A_VY01QdLgPMfHo18qfE
        9d-uOhHj32hQGwVRyVWSwXRXhSj-vAAPccNYYbWTTov5ZWin2qyo7DhH1lui
        7qzwZVGm06hQQQHJrTR81v1PU9lBClVps9s0NYr87_lQ 
    Endpoint: https://pgorelease.nianticlabs.com/plfe/528/rpc 
    Location: 
        Coordinates: 
            50.8503396 4.3517103 0.0
    """

    poko_session = PokeAuthSession(
        user,
        password,
        auth_type,
        geo_key=None
    )

    session = poko_session.authenticate(locationLookup=location)

    if session:
        global sessions
        global users
        sessions[user] = session
        users.append(user)
        logging.info(users)

        #access_token = getattr(session, "access_token", None)
        #endpoint = getattr(session, "Endpoint", None)
        #location = getattr(session, "Location", None)
        #if access_token != None and endpoint != None and location != None:
        #    return jsonify(access_token=access_token, endpoint=endpoint, location=location)
    #else:
    #    return jsonify(session), 400
    return str(session)

@app.route(BASE_PATH + "/<user>/profile")
def profile(user):
    profile = parseProfile(sessions[user].getProfile())
    return render_template('profile.html', profile=profile)


@app.route(API_PATH + "/<user>/profile")
def api_profile(user):
    return jsonify(data=parseProfile(sessions[user].getProfile()))

@app.route(API_PATH + "/<user>/items")
def items(user):
    return jsonify(data=sessions[user].getInventory())

@app.route(API_PATH + "/<user>/items/candy")
def items_candy(user):
    return jsonify(candies=sessions[user].getInventory().candies)

@app.route(BASE_PATH + "/<user>/items/eggs")
def api_eggs(user):
    eggs = sessions[user].getInventory().eggs
    list_eggs = []
    for egg in eggs:
        list_eggs.append(parseEggs(egg))
    return render_template('items_eggs.html', eggs=list_eggs)

@app.route(API_PATH + "/<user>/items/eggs")
def eggs(user):
    eggs = sessions[user].getInventory().eggs
    list_eggs = []
    for egg in eggs:
        list_eggs.append(parseEggs(egg))
    return jsonify(eggs=list_eggs)

@app.route(BASE_PATH + "/<user>/pokemons/nearby")
def pokemons_nearby(user):
    cells = sessions[user].getMapObjects()
    latitude, longitude, _ = sessions[user].getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    list_pokemons = []
    for cell in cells.map_cells:
        pokemons = [p for p in cell.wild_pokemons] + [p for p in cell.catchable_pokemons]
        for pokemon in pokemons:
            list_pokemons.append(parseWildPokemon(pokemon))

    return render_template('pokemons_nearby.html', user=user, pokemons=list_pokemons)

@app.route(API_PATH + "/<user>/pokemons/nearby")
def api_pokemons_nearby(user):
    cells = sessions[user].getMapObjects()
    latitude, longitude, _ = sessions[user].getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    list_pokemons = []
    for cell in cells.map_cells:
        pokemons = [p for p in cell.wild_pokemons]
        for pokemon in pokemons:
            list_pokemons.append(parseWildPokemon(pokemon))
    return jsonify(data=list_pokemons, count=len(list_pokemons))


@app.route(API_PATH + "/<user>/pokemons/nearby/<index_pokemon>")
def pokemons_nearby_detail(user, index_pokemon):
    """
    encounter_id: 7755420385361159741
    last_modified_timestamp_ms: 1469694984766
    latitude: 50.8503661336
    longitude: 4.35151228998
    spawn_point_id: "47c3c387213"
    pokemon_data {
      pokemon_id: ZUBAT
    }
    time_till_hidden_ms: 148718

    """
    index = int(index_pokemon) - 1

    cells = sessions[user].getMapObjects()
    latitude, longitude, _ = sessions[user].getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    list_pokemons = []
    for cell in cells.map_cells:
        pokemons = [p for p in cell.wild_pokemons]
        for pokemon in pokemons:
            list_pokemons.append(pokemon)

    return jsonify(data=parseWildPokemon(list_pokemons[index]))

@app.route(API_PATH + "/<user>/pokemons/nearby/<index_pokemon>/capture")
def pokemons_nearby_detail_capture(user, index_pokemon):
    """
    encounter_id: 7755420385361159741
    last_modified_timestamp_ms: 1469694984766
    latitude: 50.8503661336
    longitude: 4.35151228998
    spawn_point_id: "47c3c387213"
    pokemon_data {
      pokemon_id: ZUBAT
    }
    time_till_hidden_ms: 148718

    """
    index = int(index_pokemon) - 1

    cells = sessions[user].getMapObjects()
    latitude, longitude, _ = sessions[user].getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    list_pokemons = []
    for cell in cells.map_cells:
        pokemons = [p for p in cell.wild_pokemons]
        for pokemon in pokemons:
            list_pokemons.append(pokemon)

    result_capture = walkAndCatch(sessions[user], list_pokemons[index])
    return jsonify(result=str(result_capture))

@app.route(BASE_PATH + "/<user>/pokemons/party")
def pokemon_party(user):
    inventory = sessions[user].checkInventory()

    list_pokemons = []
    for pokemon in inventory.party:
        list_pokemons.append(parsePartyPokemon(pokemon))

    sorted_list = sorted(list_pokemons, key=lambda pokemon: pokemon['pokemon_id'])

    return render_template('pokemons_party.html', user=user, pokemons=sorted_list)

@app.route(API_PATH + "/<user>/pokemons/party")
def api_pokemon_party(user):
    cp = int(request.args.get('cp', 0))
    inventory = sessions[user].checkInventory()

    #app.logger.info('CP ' + str(cp))
    
    list_pokemons = []
    for pokemon in inventory.party:
        parsed_pokemon = parsePartyPokemon(pokemon)
        if cp > 0:
            #app.logger.info('Pokemon CP ' + str(parsed_pokemon['cp']) + str(parsed_pokemon['cp'] < cp))
            if parsed_pokemon['cp'] < cp:
                list_pokemons.append(parsed_pokemon)
        else:
            list_pokemons.append(parsed_pokemon)

    sorted_list = sorted(list_pokemons, key=lambda pokemon: pokemon['pokemon_id'])

    return jsonify({ 'data': sorted_list, 'count': len(sorted_list) })

@app.route(API_PATH + "/<user>/pokemons/party/<pokemon_id>")
def pokemon_party_detail(user, pokemon_id):
    inventory = sessions[user].checkInventory()

    pokemon_id = int(pokemon_id)

    for pokemon in inventory.party:
        if pokemon_id == getattr(pokemon, 'id', None):
            return jsonify({ 'data': parsePartyPokemon(pokemon, detail=True) })

    return jsonify({ 'data': {} })

@app.route(API_PATH + "/<user>/pokemons/party/<pokemon_id>/free")
def pokemon_party_free(user, pokemon_id):
    inventory = sessions[user].checkInventory()

    pokemon_id = int(pokemon_id)

    for pokemon in inventory.party:
        if pokemon_id == getattr(pokemon, 'id', None):
            result = sessions[user].releasePokemon(pokemon)
            return jsonify({ 'data': parseResponseResult(result)})

    return jsonify({ 'data': {} })

@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('error404.html'), 404

if __name__ == '__main__':
    """
    poko_session = PokeAuthSession(
        username,
        password,
        auth_type,
        geo_key=None
    )

    session = poko_session.authenticate(locationLookup='Brussels')

    if session:
        sessions[username] = session
        app.run()
    else:
        sys.exit(-1)
    """
    setupLogger()
    logging.debug('Logger set up')

    app.run()


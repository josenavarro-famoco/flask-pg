#!/usr/bin/python
import argparse
import logging
import time
import sys
import requests
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from session import PogoSession
from location import Location

from pokedex import pokedex
from inventory import items

def sendLog(type, text, latitude='', longitude=''):
    url = 'https://serene-wave-52918.herokuapp.com/'
    data = {
        'latitude': latitude,
        'longitude': longitude,
    }
    if type == 'POKESTOP':
        url += 'pokestop'
        data['name'] = text
    elif type == 'ENCOUNTER':
        url += 'encounter'
        data['pokemon'] = text
    elif type == 'PROFILE':
        url += 'profile'
        data['team'] = text
        data['pokecoin'] = latitude
        data['stardust'] = longitude
    elif type == 'STAT':
        url += 'stat'
        data['experience'] = text
        data['kms_walked'] = latitude
    else:
        url += 'log'
        data['message'] = text
    # r = requests.post(url, data = data)
    # logging.info(r.text)

def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('Line %(lineno)d,%(filename)s - %(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# Example functions
# Get profile
def getProfile(session):
        logging.info("Printing Profile:")
        profile = session.getProfile()
        logging.info(profile)
        # sendLog('PROFILE', profile.team, profile.pokecoin, profile.stardust)
        return str(profile)


def setNickname(session):
    pokemon = session.checkInventory().party[0]
    session.nicknamePokemon(pokemon, "Testing")


# Grab the nearest pokemon details
def findBestPokemon(session):
    # Get Map details and print pokemon
    logging.info("Finding Nearby Pokemon:")
    cells = session.getMapObjects()
    closest = float("Inf")
    best = -1
    pokemonBest = None
    listPokemons = []
    latitude, longitude, _ = session.getCoordinates()
    logging.info("Current pos: %f, %f" % (latitude, longitude))
    for cell in cells.map_cells:
        pokemons = [p for p in cell.wild_pokemons]
        # pokemons = [p for p in cell.wild_pokemons] + [p for p in cell.catchable_pokemons]
        # listPokemons += pokemons
        for pokemon in pokemons:
            listPokemons.append(pokemon)
            # Normalize the ID from different protos
            # pokemonId = getattr(pokemon, "pokemon_id", None)
            # if not pokemonId:
            #     pokemonId = pokemon.pokemon_data.pokemon_id
            #
            # # Find distance to pokemon
            # dist = Location.getDistance(
            #     latitude,
            #     longitude,
            #     pokemon.latitude,
            #     pokemon.longitude
            # )
            # sendLog("ENCOUNTER", pokedex[pokemonId] , pokemon.latitude , pokemon.longitude )
            # # Log the pokemon found
            # logging.info("%s, %f meters away" % (
            #     pokedex[pokemonId],
            #     dist
            # ))
            # rarity = pokedex.getRarityById(pokemonId)
            # # Greedy for rarest
            # if rarity > best:
            #     pokemonBest = pokemon
            #     best = rarity
            #     closest = dist
            # # Greedy for closest of same rarity
            # elif rarity == best and dist < closest:
            #     pokemonBest = pokemon
            #     closest = dist
    logging.info('----------- SIZE TOTAL: ' + str(len(listPokemons)))
    # return pokemonBest
    return listPokemons


# Wrap both for ease
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
        bestBall = items.UNKNOWN
        altBall = items.UNKNOWN

        # Check for balls and see if we pass
        # wanted threshold
        for i in range(len(balls)):
            if balls[i] in bag and bag[balls[i]] > 0:
                altBall = balls[i]
                if chances[i] > thresholdP:
                    bestBall = balls[i]
                    break

        # If we can't determine a ball, try a berry
        # or use a lower class ball
        if bestBall == items.UNKNOWN:
            if not berried and items.RAZZ_BERRY in bag and bag[items.RAZZ_BERRY]:
                logging.info("Using a RAZZ_BERRY")
                session.useItemCapture(items.RAZZ_BERRY, pokemon)
                berried = True
                time.sleep(delay)
                continue

            # if no alt ball, there are no balls
            elif altBall == items.UNKNOWN:
                raise GeneralPogoException("Out of usable balls")
            else:
                bestBall = altBall

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


# Do Inventory stuff
def getInventory(session):
    logging.info("Get Inventory:")
    logging.info(session.getInventory())

# Basic solution to spinning all forts.
# Since traveling salesman problem, not
# true solution. But at least you get
# those step in
def sortCloseForts(session):
    # Sort nearest forts (pokestop)
    logging.info("Sorting Nearest Forts:")
    cells = session.getMapObjects()
    latitude, longitude, _ = session.getCoordinates()
    ordered_forts = []
    for cell in cells.map_cells:
        for fort in cell.forts:
            dist = Location.getDistance(
                latitude,
                longitude,
                fort.latitude,
                fort.longitude
            )
            if fort.type == 1:
                ordered_forts.append({'distance': dist, 'fort': fort})

    ordered_forts = sorted(ordered_forts, key=lambda k: k['distance'])
    return [instance['fort'] for instance in ordered_forts]


# Find the fort closest to user
def findClosestFort(session):
    # Find nearest fort (pokestop)
    logging.info("Finding Nearest Fort:")
    return sortCloseForts(session)[0]


# Walk to fort and spin
def walkAndSpin(session, fort):
    # No fort, demo == over
    if fort:
        details = session.getFortDetails(fort)
        logging.info("Spinning the Fort \"%s\":" % details.name)

        sendLog("POKESTOP", details.name , fort.latitude , fort.longitude )
        # Walk over
        session.walkTo(fort.latitude, fort.longitude, step=3.2)
        # Give it a spin
        fortResponse = session.getFortSearch(fort)
        logging.info(fortResponse)


# Walk and spin everywhere
def walkAndSpinMany(session, forts):
    for fort in forts:
        walkAndSpin(session, fort)


# A very brute force approach to evolving
def evolveAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        logging.info(session.evolvePokemon(pokemon))
        time.sleep(1)


# You probably don't want to run this
def releaseAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        session.releasePokemon(pokemon)
        time.sleep(1)


# Just incase you didn't want any revives
def tossRevives(session):
    bag = session.checkInventory().bag
    return session.recycleItem(items.REVIVE, bag[items.REVIVE])


# Set an egg to an incubator
def setEgg(session):
    inventory = session.checkInventory()

    # If no eggs, nothing we can do
    if len(inventory.eggs) == 0:
        return None

    egg = inventory.eggs[0]
    incubator = inventory.incubators[0]
    return session.setEgg(incubator, egg)


# Understand this function before you run it.
# Otherwise you may flush pokemon you wanted.
def cleanPokemon(session, thresholdCP=50):
    logging.info("Cleaning out Pokemon...")
    party = session.checkInventory().party
    evolables = [pokedex.PIDGEY, pokedex.RATTATA, pokedex.ZUBAT]
    toEvolve = {evolve: [] for evolve in evolables}
    for pokemon in party:
        # If low cp, throw away
        if pokemon.cp < thresholdCP:
            # It makes more sense to evolve some,
            # than throw away
            if pokemon.pokemon_id in evolables:
                toEvolve[pokemon.pokemon_id].append(pokemon)
                continue

            # Get rid of low CP, low evolve value
            logging.info("Releasing %s" % pokedex[pokemon.pokemon_id])
            session.releasePokemon(pokemon)

    # Evolve those we want
    for evolve in evolables:
        candies = session.checkInventory().candies[evolve]
        pokemons = toEvolve[evolve]
        # release for optimal candies
        while candies // pokedex.evolves[evolve] < len(pokemons):
            pokemon = pokemons.pop()
            logging.info("Releasing %s" % pokedex[pokemon.pokemon_id])
            session.releasePokemon(pokemon)
            time.sleep(1)
            candies += 1

        # evolve remainder
        for pokemon in pokemons:
            logging.info("Evolving %s" % pokedex[pokemon.pokemon_id])
            logging.info(session.evolvePokemon(pokemon))
            time.sleep(1)
            session.releasePokemon(pokemon)
            time.sleep(1)


def cleanInventory(session):
    logging.info("Cleaning out Inventory...")
    bag = session.checkInventory().bag

    # Clear out all of a crtain type
    tossable = [items.POTION, items.SUPER_POTION, items.REVIVE]
    for toss in tossable:
        if toss in bag and bag[toss]:
            session.recycleItem(toss, bag[toss])

    # Limit a certain type
    limited = {
        items.POKE_BALL: 50,
        items.GREAT_BALL: 100,
        items.ULTRA_BALL: 150,
        items.RAZZ_BERRY: 25
    }
    for limit in limited:
        if limit in bag and bag[limit] > limited[limit]:
            session.recycleItem(limit, bag[limit] - limited[limit])


# Basic bot
def simpleBot(session):
    # Trying not to flood the servers
    cooldown = 1

    getProfile(session)
    getInventory(session)
    # Run the bot
    while True:
        forts = sortCloseForts(session)
        #cleanPokemon(session, thresholdCP=300)
        #cleanInventory(session)
        try:
            logging.info( '----------- FORTS: ' + str(len(forts)))
            for fort in forts:
                # pokemon = findBestPokemon(session)
                pokemons = findBestPokemon(session)
                while len(pokemons) > 0:
                    walkAndCatch(session, pokemons[0])
                    time.sleep(1)
                    pokemons = findBestPokemon(session)
                walkAndSpin(session, fort)
                cooldown = 1
                time.sleep(2)

        # Catch problems and reauthenticate
        except GeneralPogoException as e:
            logging.critical('GeneralPogoException raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)
            cooldown *= 2

        except Exception as e:
            logging.critical('Exception raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)
            cooldown *= 2

def release_pokemon(session):
    inventory = session.checkInventory()
    print "You have " + str(len(inventory.party)) + " pokemons"
    for pokemon in inventory.party:
        print pokemon
        do = input("release?? Y 1 / N 0 / back -1")
        if do == 1:
            session.releasePokemon(pokemon)
        elif do == -1:
            break

def print_menu():
    print('Select an option:')
    print('[ 0 ]: Show profile')
    print('[ 1 ]: Show inventory')
    print('[ 2 ]: Show nearby pokemons')
    print('[ 3 ]: Release pokemons')
    print('[ 4 ]: walk to closes fort')
    print('[ -1 ]: Exit')

def manual(session):
    option = 0
    suboption = 0
    while option > -1:
        print_menu()
        option = input("What do you want? ")
        if option == 0:
            getProfile(session)
        elif option == 1:
            getInventory(session)
        elif option == 2:
            while suboption > -1:
                pokemons = findBestPokemon(session)
                i = 0
                for pokemon in pokemons:
                    print pokemon
                    print("[ %s ] %s" % (str(i), pokemon.pokemon_data.pokemon_id))
                    i = i + 1
                    print '---------------'
                print('[ x ]: Catch Pokemon ?')
                print('[ -1 ]: Back')
                suboption = input("What do you want? ")
                if suboption > -1:
                    walkAndCatch(session, pokemons[suboption])
                else:
                    suboption = -1
        elif option == 3:
            release_pokemon(session)
        elif option == 4:
            suboption = 0
            forts = sortCloseForts(session)
            while suboption > -1:
                i = 0
                for fort in forts:
                    print ( "[" + str(i) + "]" + str(fort))
                    i = i + 1
                print('[ -1 ]: Back')
                suboption = input("Walk to fort? ")
                if suboption != -1:
                    print walkAndSpin(session, forts[suboption])
                    forts.remove(fort)

# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    setupLogger()
    logging.debug('Logger set up')

    token = 'eyJhbGciOiJSUzI1NiIsImtpZCI6IjM5NGNiYjk4OTdmOGZiMmYzMzY0NTMzMmEyMTU0MDk5YTk1ZTI1OWYifQ.eyJpc3MiOiJhY2NvdW50cy5nb29nbGUuY29tIiwiYXVkIjoiODQ4MjMyNTExMjQwLTdzbzQyMWpvdHIyNjA5cm1xYWtjZXV1MWx1dXEwcHRiLmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29tIiwic3ViIjoiMTExNjc4NjkwMjc5NTg4MzQ5MTIxIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsImF6cCI6Ijg0ODIzMjUxMTI0MC0zdmRydHJmZG50bGpmMnU0bWxndG5ubGhuaWduMzVkNS5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSIsImVtYWlsIjoiam04bmF2QGdtYWlsLmNvbSIsImlhdCI6MTQ2OTkxNzkxNiwiZXhwIjoxNDY5OTIxNTE2LCJuYW1lIjoiSm9zZSBNaWd1ZWwgTmF2YXJybyBJZ2xlc2lhcyIsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vLVh1Zzk3b2F2TXljL0FBQUFBQUFBQUFJL0FBQUFBQUFBVThZL2lkc0VneDBkU0tFL3M5Ni1jL3Bob3RvLmpwZyIsImdpdmVuX25hbWUiOiJKb3NlIE1pZ3VlbCIsImZhbWlseV9uYW1lIjoiTmF2YXJybyBJZ2xlc2lhcyJ9.d1W12odZnEScMvDGD643P9uIQ3IuycMmZFDwHKm1I8ILKYgz2bKUro_D47qer3muZajTXuehJ32Hjel3MPbb5H_DoOyO1AkzROHy6_EdxxBR_uM5jkMWUtFc1FRguZ8T47sFMR0-1ckCdP6S3ymvBiMkMA8rXj5QHljcT8tsMEf2HQ5iABYUYZ-gpmBwGEebTwzsBQQaN_m9JXe1nWoQcsC33unaLVOHUekRF7p3q8HyX-TDwPaDeMmgrEJR5dEFQjjthNyaJOo1AbkW-5guFrYvHAkdrwS8eHJS_LxZh0z902SRQR-cA8WBZRxkkZA0EvqGITniich12xG6ABVRGA'
    location = Location('Brussels', None)
    req_session = PokeAuthSession.createRequestsSession()
    session = PogoSession(req_session, 'google', token, location)

    if session:
        manual(session)
    else:
        logging.critical('Session not created successfully')
        sys.exit(-1)

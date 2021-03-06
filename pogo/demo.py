#!/usr/bin/python
import argparse
import logging
import time
import sys
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

from pokedex import pokedex
from inventory import items

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
        #pokemons = [p for p in cell.wild_pokemons] + [p for p in cell.catchable_pokemons]
        pokemons = [p for p in cell.wild_pokemons] 
        # listPokemons += pokemons
        for pokemon in pokemons:
            listPokemons.append(pokemon)
            # Normalize the ID from different protos
            pokemonId = getattr(pokemon, "pokemon_id", None)
            if not pokemonId:
                pokemonId = pokemon.pokemon_data.pokemon_id

            # Find distance to pokemon
            dist = Location.getDistance(
                latitude,
                longitude,
                pokemon.latitude,
                pokemon.longitude
            )

            logging.info("%s, %f meters away" % (
                pokedex[pokemonId],
                dist
            ))
            rarity = pokedex.getRarityById(pokemonId)
            # Greedy for rarest
            if rarity > best:
                pokemonBest = pokemon
                best = rarity
                closest = dist
            # Greedy for closest of same rarity
            elif rarity == best and dist < closest:
                pokemonBest = pokemon
                closest = dist
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

        session.walkTo(fort.latitude, fort.longitude, step=3.2)
        # Give it a spin
        fortResponse = session.getFortSearch(fort)
        logging.info(fortResponse)


# Walk and spin everywhere
def walkAndSpinMany(session, forts):
    for fort in forts:
        walkAndSpin(session, fort)

def setEggtoIncubator(session):
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

    empty:
    id: "EggIncubatorProto4824214944684084552"
    item_id: ITEM_INCUBATOR_BASIC_UNLIMITED
    incubator_type: INCUBATOR_DISTANCE

    full:
    id: "EggIncubatorProto4824214944684084552"
    item_id: ITEM_INCUBATOR_BASIC_UNLIMITED
    incubator_type: INCUBATOR_DISTANCE
    pokemon_id: 8929306760488893465
    start_km_walked: 158.82093811
    target_km_walked: 163.82093811
    """
    inventory = session.getInventory()
    for incubator in inventory.incubators:
        #if getattr(incubator, "item_id", None) == 'ITEM_INCUBATOR_BASIC_UNLIMITED':
        #if getattr(incubator, "pokemon_id", None) == None:
        for egg in inventory.eggs:
            result = session.setEgg(incubator, egg)
            logging.info(result)
            if result != 'ERROR_INCUBATOR_ALREADY_IN_USE':
                break
                #logging.info(session.setEgg(incubator, egg))
            #if getattr(egg, "egg_incubator_id", None) == None:
            #    logging.info(session.setEgg(incubator, egg))

# Basic bot
def simpleBot(session):
    # Trying not to flood the servers
    cooldown = 1

    getProfile(session)
    getInventory(session)
    # Run the bot
    while True:
        forts = sortCloseForts(session)
        setEggtoIncubator(session)
        try:
            logging.info( '----------------------------------------- FORTS: ' + str(len(forts)))
            for fort in forts:
                # pokemons = findBestPokemon(session)
                # #if len(pokemons) > 0:
                # #    walkAndCatch(session, pokemons[0])
                # while len(pokemons) > 0:
                #     walkAndCatch(session, pokemons[0])
                #     time.sleep(1)
                #     pokemons = findBestPokemon(session)
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


# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    setupLogger()
    logging.debug('Logger set up')

    # Read in args
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--auth", help="Auth Service", required=True)
    parser.add_argument("-u", "--username", help="Username", required=True)
    parser.add_argument("-p", "--password", help="Password", required=True)
    parser.add_argument("-l", "--location", help="Location")
    parser.add_argument("-g", "--geo_key", help="GEO API Secret")
    args = parser.parse_args()

    # Check service
    if args.auth not in ['ptc', 'google']:
        logging.error('Invalid auth service {}'.format(args.auth))
        sys.exit(-1)

    # Create PokoAuthObject
    poko_session = PokeAuthSession(
        args.username,
        args.password,
        args.auth,
        geo_key=args.geo_key
    )

    if args.location:
        session = poko_session.authenticate(locationLookup=args.location)
    else:
        session = poko_session.authenticate()

    if session:
        if args.location:
            simpleBot(session)

    else:
        logging.critical('Session not created successfully')

import struct
import time

import requests

def f2i(float):
    return struct.unpack('<Q', struct.pack('<d', float))[0]


def f2h(float):
    return hex(struct.unpack('<Q', struct.pack('<d', float))[0])


def h2f(hex):
    return struct.unpack('<d', struct.pack('<Q', int(hex, 16)))[0]


def encodeLocation(loc):
    return (f2i(loc.latitude), f2i(loc.longitude), f2i(loc.altitude))


def getMs():
    return int(round(time.time() * 1000))

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
    #r = requests.post(url, data = data)
# installer for meteo.cam
# Copyright 2018 Ingo Oppermann

from setup import ExtensionInstaller

def loader():
    return MeteoCamInstaller()

class MeteoCamInstaller(ExtensionInstaller):
    def __init__(self):
        super(MeteoCamInstaller, self).__init__(
            version="0.1",
            name='meteocam',
            description='Upload weather data to meteo.cam',
            author="Ingo Oppermann",
            author_email="ingo@oppermann.ch",
            restful_services='user.meteocam.MeteoCam',
            config={
                'StdRESTful': {
                    'MeteoCam': {
                        'enable': 'true',
                        'station_key': 'INSERT_KEY_HERE',
                        'station_id': 'INSERT_ID_HERE'}}},
            files=[('bin/user', ['bin/user/meteocam.py'])]
            )

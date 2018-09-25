# weeWX extension to send data to meteo.cam

meteo.cam is a free service where you can publish your weather data.


## Requirement

- meteo.cam account with a registered weather station [https://meteo.cam/](https://meteo.cam/)
- weeWX 3.x [http://weewx.com/downloads/](http://weewx.com/downloads/)


## Credentials

In order to upload your the weather data to meteo.cam you need to register your weather station
at meteo.cam.

The required credentials for uploading weather data are the _key_ and the _ID_ for your registered
weather station.

You find them when you go to your meteo.cam dashboard and click on "EDIT" next to the
weather station name. There is the station ID. Click on "UPLOAD" and you'll find the station key.


## Installation

First you need to clone the repo

```
git clone https://github.com/ioppermann/weewx-meteocam
```

Then install the meteo.cam extension with the extension manager

```
/path/to/weewx/bin/wee_extension --install=/path/to/weewx-meteocam
```

You will need to insert the values for your meteo.cam station key
and station ID accordingly.

```
[StdRESTful]
    [[MeteoCam]]
        enable = true
        station_key = "INSERT_KEY_HERE"
        station_id = "INSERT_ID_HERE"
```

After adjusting the config file you have to restart weeWX

```
sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
```

## License

This module is distributed under the BSD license. Refer to [LICENSE](/blob/master/LICENSE).

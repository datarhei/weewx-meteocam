# Copyright 2018 Ingo Oppermann

#==============================================================================
# meteo.cam
#==============================================================================
# Upload data to meteo.cam (https://meteo.cam)
#
# To enable this module, put this file in bin/user, add the following to
# weewx.conf, then restart weewx.
#
# [[MeteoCam]]
#     enable = true
#     station_key = your meteo.cam weather station key
#     station_id = your meteo.cam weather station id
#

import Queue
import hashlib
import sys
import syslog
import time
import urllib
import urllib2

import weewx
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool, accumulateLeaves

if weewx.__version__ < "3":
    raise weewx.UnsupportedFeature("weewx 3 is required, found %s" % weewx.__version__)

#==============================================================================
# MeteoCam
#==============================================================================

class MeteoCam(weewx.restx.StdRESTful):
    """Upload data to meteo.cam

    URL=https://pws.meteo.cam/v1/observe/<key>/<id>
    """

    def __init__(self, engine, config_dict):
        super(MeteoCam, self).__init__(engine, config_dict)
        print "hello meteo.cam"
        syslog.syslog(syslog.LOG_INFO, "restx: MeteoCam: ")

        site_dict = get_site_dict(config_dict, 'MeteoCam', 'station_key', 'station_id')
        if site_dict is None:
            return

        site_dict['manager_dict'] = weewx.manager.get_manager_dict_from_config(config_dict, 'wx_binding')

        site_dict.setdefault('log_success', False)
        site_dict.setdefault('log_failure', False)
        site_dict.setdefault('max_backlog', 0)
        site_dict.setdefault('max_tries', 1)

        self.cached_values = CachedValues()
        self.loop_queue = Queue.Queue()
        self.loop_thread = MeteoCamThread(self.loop_queue, **site_dict)
        self.loop_thread.start()
        #self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        print "restx: MeteoCam: Data will be uploaded for weather station %s" % site_dict['station_id']
        syslog.syslog(syslog.LOG_INFO, "restx: MeteoCam: "
                      "Data will be uploaded for weather station %s" %
                      site_dict['station_id'])

    def new_loop_packet(self, event):
        """Puts new LOOP packets in the loop queue"""
        self.cached_values.update(event.packet, event.packet['dateTime'])
        self.loop_queue.put(self.cached_values.get_packet(event.packet['dateTime']))

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)

#==============================================================================
# MeteoCamThread
#==============================================================================

class MeteoCamThread(weewx.restx.RESTThread):

    # URL to publish data to
    _SERVER_URL = 'https://pws.meteo.cam/v1/observe/<key>/<id>'

    # Types and formats of the data to be published:
    _FORMATS = {'barometer'  : 'baromhpa=%.3f', #hPa
                'outTemp'    : 'tempc=%.1f', # C
                'outHumidity': 'humidity=%.0f',
                'windSpeed'  : 'windspeedms=%.1f', # m/s
                'windDir'    : 'winddir=%.0f',
                'windGust'   : 'windgustms=%.1f', # m/s
                'dewpoint'   : 'dewptc=%.1f', # C
                'hourRain'   : 'rainmm=%.2f', # mm
                'dayRain'    : 'dailyrainmm=%.2f', # mm
                'radiation'  : 'solarradiation=%.2f',
                'UV'         : 'UV=%.2f',
                'soilTemp1'  : "soiltempc=%.1f", # C
                'soilMoist1' : "soilmoisture=%.0f",
                'leafWet1'   : "leafwetness=%.0f"}

    def __init__(self, queue, station_key, station_id,
                 manager_dict=None, server_url=_SERVER_URL, skip_upload=False,
                 post_interval=5, max_backlog=sys.maxint, stale=None,
                 log_success=True, log_failure=True, 
                 timeout=60, max_tries=3, retry_wait=5):
        """Initialize an instance of MeteoCamThread.

        Required parameters:

        station_key: meteo.cam weather station key
        station_id: meteo.cam weather station ID
        """
        super(MeteoCamThread, self).__init__(queue,
                                           protocol_name='MeteoCam',
                                           manager_dict=manager_dict,
                                           post_interval=post_interval,
                                           max_backlog=max_backlog,
                                           stale=stale,
                                           log_success=log_success,
                                           log_failure=log_failure,
                                           timeout=timeout,
                                           max_tries=max_tries,
                                           retry_wait=retry_wait)
        self.key = station_key
        self.id = station_id
        self.server_url = server_url
        self.skip_upload = to_bool(skip_upload)

        self.formats = dict(MeteoCamThread._FORMATS)

        # Assemble the URL
        self.server_url = self.server_url.replace('<key>', station_key)
        self.server_url = self.server_url.replace('<id>', station_id)

        print "started MeteoCam thread"

    def check_response(self, response):
        error = True
        for line in response:
            if line.find('OK'):
                error=False

        if error:
            raise weewx.restx.FailedPost("server returned '%s'" % ', '.join(response))

    def format_url(self, in_record):

        # Convert to units required by meteo.cam
        record = weewx.units.to_METRICWX(in_record)

        # assemble an array of values in the proper order
        values = ["dateutc=now"]

        # Go through each of the supported types, formatting it, then adding it to values:
        for key in self.formats:
            val = record.get(key)
            # Check to make sure the type is not null
            if val is not None:
                # Format the value, and accumulate in values:
                values.append(self.formats[key] % val)

        valstr = '&'.join(values)
        url = self.server_url + '?' + valstr
        print "restx: MeteoCam: url: %s" % url
        syslog.syslog(syslog.LOG_DEBUG, 'restx: MeteoCam: url: %s' % url)
        return url

############################# HELPER ####################################

class CachedValues(object):
    """Dictionary of value-timestamp pairs.  Each timestamp indicates when the
    corresponding value was last updated."""

    def __init__(self):
        self.unit_system = None
        self.values = dict()

    def update(self, packet, ts):
        # update the cache with values from the specified packet, using the
        # specified timestamp.
        for k in packet:
            if k is None:
                # well-formed packets do not have None as key, but just in case
                continue
            elif k == 'dateTime':
                # do not cache the timestamp
                continue
            elif k == 'usUnits':
                # assume unit system of first packet, then enforce consistency
                if self.unit_system is None:
                    self.unit_system = packet['usUnits']
                elif packet['usUnits'] != self.unit_system:
                    raise ValueError("Mixed units encountered in cache. %s vs %s" % \
                                     (self.unit_sytem, packet['usUnits']))
            else:
                # cache each value, associating it with the it was cached
                self.values[k] = {'value': packet[k], 'ts': ts}

    def get_value(self, k, ts, stale_age):
        # get the value for the specified key.  if the value is older than
        # stale_age (seconds) then return None.
        if k in self.values and ts - self.values[k]['ts'] < stale_age:
            return self.values[k]['value']
        return None

    def get_packet(self, ts=None, stale_age=960):
        if ts is None:
            ts = int(time.time() + 0.5)
        pkt = {'dateTime': ts, 'usUnits': self.unit_system}
        for k in self.values:
            pkt[k] = self.get_value(k, ts, stale_age)
        return pkt

def get_site_dict(config_dict, service, *args):
    """Obtain the site options, with defaults from the StdRESTful section.
    If the service is not enabled, or if one or more required parameters is
    not specified, then return None."""

    try:
        site_dict = accumulateLeaves(config_dict['StdRESTful'][service],
                                     max_level=1)
    except KeyError:
        syslog.syslog(syslog.LOG_INFO, "restx: %s: "
                                       "No config info. Skipped." % service)
        return None

    # If site_dict has the key 'enable' and it is False, then
    # the service is not enabled.
    try:
        if not to_bool(site_dict['enable']):
            syslog.syslog(syslog.LOG_INFO, "restx: %s: "
                                           "Posting not enabled." % service)
            return None
    except KeyError:
        pass

    # At this point, either the key 'enable' does not exist, or
    # it is set to True. Check to see whether all the needed
    # options exist, and none of them have been set to 'replace_me':
    try:
        for option in args:
            if site_dict[option] == 'replace_me':
                raise KeyError(option)
    except KeyError, e:
        syslog.syslog(syslog.LOG_DEBUG, "restx: %s: "
                                        "Data will not be posted: Missing option %s" %
                      (service, e))
        return None

    # Get logging preferences from the root level
    if config_dict.get('log_success') is not None:
        site_dict.setdefault('log_success', config_dict.get('log_success'))
    if config_dict.get('log_failure') is not None:
        site_dict.setdefault('log_failure', config_dict.get('log_failure'))

    # Get rid of the no longer needed key 'enable':
    site_dict.pop('enable', None)

    return site_dict

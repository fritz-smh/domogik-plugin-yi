#!/usr/bin/python
# -*- coding: utf-8 -*-

""" This file is part of B{Domogik} project (U{http://www.domogik.org}).

License
=======

B{Domogik} is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

B{Domogik} is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Domogik. If not, see U{http://www.gnu.org/licenses}.

Plugin purpose
==============

Xiaomi Yi Ants camera (with rtsp support)

Implements
==========

- YiManager

@author: Fritz <fritz.smh@gmail.com>
@copyright: (C) 2007-2016 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

from domogik.common.plugin import Plugin

from domogik_packages.plugin_yi.lib.yi import Yi
from domogikmq.message import MQMessage
import threading
import traceback
import os


class YiManager(Plugin):
    """ Get disk free size over xPL
    """

    def __init__(self):
        """ Init plugin
        """
        Plugin.__init__(self, name='yi')

        # check if the plugin is configured. If not, this will stop the plugin and log an error
        if not self.check_configured():
            return

        # get the config
        self.ffserver_ip = self.get_config("ffserver_ip")
        self.ffserver_port = int(self.get_config("ffserver_port"))
        self.motion_files_history = self.get_config("motion_files_history")

        # get the devices list
        self.devices = self.get_device_list(quit_if_no_device = True)

        # send sensor values
        self.send_sensor_yi_values()
 
        # generate the ffserver.conf file
        ffserver_file = os.path.join(self.get_data_files_directory(), "ffserver.conf")
        self.yi = Yi(self.log, self.get_stop(), ffserver_file, self.ffserver_ip, self.ffserver_port, self.devices, self.get_parameter)
        self.yi.generate_ffserver_config()

        # start checking for motion (each minute) on all yi
        threads = {}
        for a_device in self.devices:
            ip = self.get_parameter(a_device, "ip")
            do_download = self.get_parameter(a_device, "download_motion_files")
            sensor_motion_id = a_device['sensors']['motion']['id']
            sensor_motion_file_id = a_device['sensors']['motion_file']['id']
            thr_name = "dev_{0}".format(a_device['id'])
            threads[thr_name] = threading.Thread(None,
                                          self.yi.check_motion,
                                          thr_name,
                                          (ip, sensor_motion_id, sensor_motion_file_id, self.send_sensor_value, self.get_publish_files_directory, do_download),
                                          {})
            threads[thr_name].start()
            self.register_thread(threads[thr_name])

        # start the cleaning motion files process
        thr_clean = threading.Thread(None,
                                     self.yi.clean_motion_files,
                                     "clean",
                                     (self.motion_files_history, self.get_publish_files_directory),
                                     {})
        thr_clean.start()
        self.register_thread(thr_clean)

        # start streaming
        thr_stream = threading.Thread(None,
                                     self.yi.ffserver_start,
                                     "stream",
                                     (),
                                     {})
        thr_stream.start()
        self.register_thread(thr_stream)

        self.ready()



    def send_sensor_yi_values(self):
        """ Send the sensor values
            This plugin is a special case : the sensor values is sent only on plugin startup and are the urls of the Yi cameras
        """
        data = {}
    
        idx = 1
        for a_device in self.devices:
            url = "http://{0}:{1}/yi{2}.mjpeg".format(self.ffserver_ip, self.ffserver_port, idx)
            sensor_id = a_device['sensors']['yi']['id']
            idx += 1

            data[sensor_id] = url

            try:
                self._pub.send_event('client.sensor', data)
                self.log.info(u"Publish data for device '{0}' sended = {1}".format(a_device["name"], data))
            except:
                # We ignore the message if some values are not correct ...
                self.log.error(u"Error while sending sensor data. MQ data is : '{0}'. Error is : {1}".format(data, traceback.format_exc()))


    def send_sensor_value(self, id, value):
        data = {}
        data[id] = value
        try:
            self._pub.send_event('client.sensor', data)
            self.log.info(u"Publish data for sensor id '{0}' sended = {1}".format(id, value))
        except:
            # We ignore the message if some values are not correct ...
            self.log.error(u"Error while sending sensor data. MQ data is : '{0}'. Error is : {1}".format(value, traceback.format_exc()))

    def on_mdp_request(self, msg):
        """ Called when a MQ req/rep message is received
        """
        Plugin.on_mdp_request(self, msg)
        if msg.get_action() == "client.cmd":
            data = msg.get_data()
            self.log.info(u"==> Received 0MQ messages data: %s" % format(data))
            # ==> Received 0MQ messages data: {u'command_id': 35, u'value': u'1', u'device_id': 112}
            # ==> Received 0MQ messages data: {u'command_id': 36, u'value': u'128', u'device_id': 113}
            # ==> Received 0MQ messages data: {u'command_id': 37, u'value': u'Bonjour', u'device_id': 114}

            # search for related device
            for a_device in self.devices:
                for a_cmd in a_device['commands']:
                    if data['command_id'] == a_device['commands'][a_cmd]['id']:
                        # As we will just execute a shell script, we can't really known if the command will be ok and how long it will take...
                        # so we respond first on MQ to say we got the request

                        self.log.info("Reply to command 0MQ")
                        reply_msg = MQMessage()
                        reply_msg.set_action('client.cmd.result')
                        reply_msg.add_data('status', True)
                        reply_msg.add_data('reason', '')
                        self.reply(reply_msg.get())

                        # Now, launch the speak action !
                        ip = self.get_parameter(a_device, "ip")
                        lang = 'fr-FR'
                        thr_speak = threading.Thread(None,
                                                     self.yi.speak,
                                                     "speak",
                                                     (ip, lang, data['text'], self.get_data_files_directory),
                                                     {})
                        thr_speak.start()
        self.register_thread(thr_speak)



if __name__ == "__main__":
    YiManager()

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

Manage Yi camera and ffmpeg to convert rtsp to mjpeg

Implements
==========

- Yi

@author: Fritz <fritz.smh@gmail.com>
@copyright: (C) 2007-2016 Domogik project
@license: GPL(v3)
@organization: Domogik
"""

import os
import traceback
from subprocess import Popen, PIPE
import signal
import time
# python 2 and 3
try:
    from urllib.request import urlopen
except ImportError:
    from urllib import urlopen


class Yi:
    """ Yi camera
    """

    def __init__(self, log, stop, ffserver_file, ffserver_ip, ffserver_port, devices, get_parameter):
        """ Init Yi object
            @param log : log instance
            @param stop : stop
        """
        self.log = log
        self._stop = stop
        self.ffserver_file = ffserver_file
        self.ffserver_ip = ffserver_ip
        self.ffserver_port = ffserver_port
        self.devices = devices
        self.get_parameter = get_parameter

    def generate_ffserver_config(self):
        ### build ACL for all cameras
        acl = ""
        acl += "    ACL allow localhost\n"
        acl += "    ACL allow 127.0.0.1\n"


        ### config file header
        data = "Port {0}\n".format(self.ffserver_port)
        data += "BindAddress 0.0.0.0\n"
        data += "MaxClients 10\n"
        data += "MaxBandWidth 500000\n"
        data += "CustomLog -\n"
        data += "#NoDaemon\n"

        ### Devices parts
        idx = 1
        for a_device in self.devices:
            data += "<Feed yi{0}.ffm>\n".format(idx)
            data += "    File /tmp/yi{0}.ffm\n".format(idx)
            data += "    FileMaxSize 1G\n"
            data += acl
            data += "</Feed>\n"
            data += "<Stream yi{0}.mjpeg>\n".format(idx)
            data += "    Feed yi{0}.ffm\n".format(idx)
            data += "    Format mpjpeg\n"
            data += "    VideoFrameRate 25\n"
            data += "    VideoBitRate 10240\n"
            data += "    VideoBufferSize 20480\n"
            data += "    VideoSize 640x360\n"
            data += "    VideoQMin 3\n"
            data += "    VideoQMax 31\n"
            data += "    NoAudio\n"
            data += "    Strict -1\n"
            data += "</Stream>\n"

            idx += 1

        ### Stats url
        data += "<Stream stat.html>\n"
        data += "    Format status\n"
        data += "    # Only allow local people to get the status\n"
        data += "    ACL allow localhost\n"
        data += "    ACL allow 192.168.0.0 192.168.255.255\n"
        data += "</Stream>\n"

        ### Save the file
        fo = open(self.ffserver_file, "w")
        self.log.info("Saving ffserver configuration to file '{0}' : \n{1}".format(self.ffserver_file, data))
        fo.write(data)
        fo.close()

    def ffserver_start(self):
        ### Start ffserver
        self.log.info("Before starting ffserver, in case it already runs, we kill it...")
        self.ffserver_stop()
        self.log.info("Start ffserver")
        cmd = "ffserver -f {0} > {0}.log 2>&1 &".format(self.ffserver_file)
        self.log.info(u"Execute command : {0}".format(cmd))
        subp = Popen(cmd, 
                     shell=True)
        pid = subp.pid
        subp.communicate()

        ### wait a little
        time.sleep(5)

        ### Start streaming of each camera
        pids = {}

        # eternal loop to be sure that all cameras are responding...
        while not self._stop.isSet():
            idx = 1
            for a_device in self.devices:
                ### do we need to (re)start the camera streaming ?
                restart = False
                if a_device['name'] not in pids:
                    restart = True
                else:
                    # as the pid does not exist after... we will do a grep to find the forked process of ffmpeg
                    cmd_pid = "ps -ef | grep \"ffmpeg -i rtsp://{0}:554/ch0_1.h264\" | grep -v grep | awk '{{ print $2 }}'".format(ip)
                    subp = Popen(cmd_pid, 
                                 stdout=PIPE,
                                 shell=True)
                    pid = subp.pid
                    the_pid = subp.communicate()[0].strip()
                    if the_pid == "":
                        self.log.warning(u"No more camera stream for the camera '{0}' !!!".format(a_device['name']))
                        restart = True
                    else:
                        pids[a_device['name']] = the_pid
                        self.log.debug(u"Camera stream for the camera '{0}' still alive. Pid is '{1}'".format(a_device['name'], the_pid))

                if restart == False:
                    continue

                ### start streaming
                self.log.info(u"Start streaming camera '{0}'".format(a_device['name']))
                ip = self.get_parameter(a_device, "ip")
                cmd = 'ffmpeg -i "rtsp://{0}:554/ch0_1.h264" http://{1}:{2}/yi{3}.ffm &'.format(ip, "localhost", self.ffserver_port, idx)
                self.log.info(u"Execute command : {0}".format(cmd))
                subp = Popen(cmd, 
                             shell=True)
                pid = subp.pid
                subp.communicate()
    
                # get the streaming pid
                cmd_pid = "ps -ef | grep \"ffmpeg -i rtsp://{0}:554/ch0_1.h264\" | grep -v grep | awk '{{ print $2 }}'".format(ip)
                subp = Popen(cmd_pid, 
                             stdout=PIPE,
                             shell=True)
                pid = subp.pid
                the_pid = subp.communicate()[0].strip()
                pids[a_device['name']] = the_pid

                idx += 1
    

            # each 60s we check again all cameras stream processes
            self._stop.wait(60)


    def ffserver_stop(self):
        self.log.info("Stop ffserver")
        self.log.debug("Find if there is any 'ffserver' process running")
        p = Popen(['ps', '-A'], stdout=PIPE)
        out, err = p.communicate()
        for line in out.splitlines():
            if 'ffserver' in line:
                self.log.debug("Found process : '{0}'. Killing it...".format(line))
                pid = int(line.split(None, 1)[0])
                os.kill(pid, signal.SIGKILL)


    def check_motion(self, ip, sensor_motion_id, sensor_motion_file_id, cb_send_sensor_value, cb_get_publish_files_directory, do_download):
        """ Check for motion on a yi camera
        """
        self.log.info("Start loop to check for motions on Yi with ip '{0}'".format(ip))
        url = "http://{0}/motion".format(ip)

        raw_data_old = ""
        while not self._stop.isSet():
            # we wait 30s instead of 60s to avoid  losing 1 motion video
            self._stop.wait(30)

            self.log.debug(u"Check motion by calling '{0}'".format(url))
            try:
                response = urlopen(url)
                raw_data = response.read().decode('utf-8').strip()
                self.log.debug(u"Raw data : {0}".format(raw_data))
            except:
                raw_data = ""
                self.log.warning(u"Error while calling url '{0}'. Error is : {1}".format(url, traceback.format_exc()))

            # motion!!
            if raw_data != "":
                # process only if not already processed ;) (because we sleep only 30s instead of 60s)
                if raw_data != raw_data_old:
                    self.log.debug(u"Motion detected on Yi with ip '{0}'".format(ip))
                    # set motion
                    cb_send_sensor_value(sensor_motion_id, 1)

                    # download the video file
                    video_url = "http://{0}/{1}".format(ip, raw_data)
                    if do_download in [True, 'True', 'y']:
                        video_file = os.path.join(cb_get_publish_files_directory(), "{0}_{1}".format(ip, raw_data.replace("/", "")))
                        self.log.debug("Downloading video file '{0}' as '{1}'".format(video_url, video_file))
                        fdata = urlopen(video_url)
                        dl_file = open(video_file, "wb")
                        dl_file.write(fdata.read())
                        dl_file.close()
                        cb_send_sensor_value(sensor_motion_file_id, "publish://{0}".format(raw_data.replace("/", "")))
                    else:
                        cb_send_sensor_value(sensor_motion_file_id, video_url)

           
            # no motion!!
            else:
                self.log.debug(u"No motion detected on Yi with ip '{0}'".format(ip))
                cb_send_sensor_value(sensor_motion_id, 0)

    def clean_motion_files(self, nb_days, cb_get_publish_files_directory):
        """ Clean files older than nb_days
        """
        nb_days = int(nb_days)

        while not self._stop.isSet():
            cmd_list = "find {0} -mtime +{1}".format(cb_get_publish_files_directory(), nb_days)
            cmd_rm = "find {0} -mtime +{1} -exec rm {{}} \;".format(cb_get_publish_files_directory(), nb_days)
    
            subp = Popen(cmd_list, 
                         shell=True,
                         stdout=PIPE)
            pid = subp.pid
            file_list = subp.communicate()[0]
    
            self.log.info(u"The following files, older than '{0}' days will be deleted : \n{1}".format(nb_days, file_list))
            self.log.info(u"Deleting the files... starting")
            subp = Popen(cmd_rm, 
                         shell=True)
            pid = subp.pid
            subp.communicate()
            self.log.info(u"Deleting the files... finished!")

            # wait 1 hour
            self._stop.wait(3600)
 
    def speak(self, ip, lang, text, get_data_files_directory):
        self.log.info("Make the camera '{0}' speak in '{1}' the text '{2}'...".format(ip, lang, text))
        cmd = '{0}/speak.sh {1} {2} "{3}"'.format(get_data_files_directory(), ip, lang, text)
        self.log.info(u"Execute command : {0}".format(cmd))
        subp = Popen(cmd, 
                     stdout = PIPE,
                     shell=True)
        pid = subp.pid
        #subp.communicate()
        out, err = subp.communicate()
        for line in out.splitlines():
            self.log.debug("   {0}".format(line))


###
# Copyright (c) 2002-2004, Jeremiah Fincher
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###



import time

import supybot.log as log
import supybot.conf as conf
import supybot.ircdb as ircdb
import supybot.drivers as drivers
import supybot.ircmsgs as ircmsgs

from twisted.internet import reactor, error
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ReconnectingClientFactory

class TwistedRunnerDriver(drivers.IrcDriver):
    def name(self):
        return self.__class__.__name__

    def run(self):
        try:
            reactor.iterate(conf.supybot.drivers.poll())
        except:
            drivers.log.exception('Uncaught exception outside reactor:')

class SupyIrcProtocol(LineReceiver):
    delimiter = '\n'
    MAX_LENGTH = 1024
    def __init__(self):
        self.mostRecentCall = reactor.callLater(1, self.checkIrcForMsgs)

    def lineReceived(self, line):
        start = time.time()
        msg = drivers.parseMsg(line)
        if msg is not None:
            self.irc.feedMsg(msg)

    def checkIrcForMsgs(self):
        if self.connected:
            msg = self.irc.takeMsg()
            if msg:
                self.transport.write(str(msg))
        self.mostRecentCall = reactor.callLater(1, self.checkIrcForMsgs)

    def connectionLost(self, r):
        self.mostRecentCall.cancel()
        if r.check(error.ConnectionDone):
            drivers.log.disconnect(self.factory.currentServer)
        else:
            drivers.log.disconnect(self.factory.currentServer, errorMsg(r))
        if self.irc.zombie:
            self.factory.continueTrying = False
            while self.irc.takeMsg():
                continue
        else:
            self.irc.reset()

    def connectionMade(self):
        self.factory.resetDelay()
        self.irc.driver = self

    def die(self):
        drivers.log.die(self.irc)
        self.factory.continueTrying = False
        self.transport.loseConnection()

    def reconnect(self, wait=None):
        # We ignore wait here, because we handled our own waiting.
        drivers.log.reconnect(self.irc.network)
        self.transport.loseConnection()

def errorMsg(reason):
    return reason.getErrorMessage()

class SupyReconnectingFactory(ReconnectingClientFactory, drivers.ServersMixin):
    # XXX Shouldn't the maxDelay be configurable?
    maxDelay = 300
    protocol = SupyIrcProtocol
    def __init__(self, irc):
        self.irc = irc
        drivers.ServersMixin.__init__(self, irc)
        (server, port) = self._getNextServer()
        vhost = conf.supybot.protocols.irc.vhost()
        reactor.connectTCP(server, port, self, bindAddress=(vhost, 0))

    def clientConnectionFailed(self, connector, r):
        drivers.log.connectError(self.currentServer, errorMsg(r))
        (connector.host, connector.port) = self._getNextServer()
        if not r.check(error.TimeoutError):
            ReconnectingClientFactory.clientConnectionFailed(self, connector,r)

    def clientConnectionLost(self, connector, r):
        (connector.host, connector.port) = self._getNextServer()
        ReconnectingClientFactory.clientConnectionLost(self, connector, r)

    def startedConnecting(self, connector):
        drivers.log.connect(self.currentServer)

    def buildProtocol(self, addr):
        protocol = ReconnectingClientFactory.buildProtocol(self, addr)
        protocol.irc = self.irc
        return protocol


Driver = SupyReconnectingFactory

try:
    ignore(poller)
except NameError:
    poller = TwistedRunnerDriver()
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
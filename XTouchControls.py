from enum import Enum
from datetime import datetime
import threading
import _thread
import socket
from time import sleep
import sys
import mido

class XTouch:

	def __init__(self, ip):
		self.ip = ip
		self.channels = []
		for i in range(9):
			self.channels.append(self.Channel(self, i))
		self.buttons = self.Buttons(self)
		self.onButtonChange = None
		self.onSliderChange = None
		self.onEncoderChange = None
		self._active = True
		self.connect()

	@property
	def active(self):
		return self._active

	@active.setter
	def active(self, val: bool):
		self._active = val
		self.SendAll()

	def setOnButtonChange(self, callback):
		self.onButtonChange = callback

	def setOnSliderChange(self, callback):
		self.onSliderChange = callback

	def setOnEncoderChange(self, callback):
		self.onEncoderChange = callback

	def connect(self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.sock.bind(('', 10111))
		_thread.start_new_thread(self.getMsg, ())
		self.running = True
		self.SendKeepAlive()
		print("Connected")

	def getMsg(self):
		while self.running:
			data, addr = self.sock.recvfrom(10111)
			self.HandleMsg(data)

	def sendRawMsg(self, list):
		if self._active:
			self.sock.sendto(bytearray(list), (self.ip, 10111))
			#sleep(0.002)

	def sendMidiControl(self, index, value):
		self.sendRawMsg(bytearray([0xF0, 0xD0, index, value, 0xF7]))

	def SendAll(self):
		for c in self.channels:
			c.SendAll()
		for b in self.buttons:
			self.SendButton(b)

	def SendButton(self, index, value):
		self.sendRawMsg(bytearray([0xF0, 0x90, 0x00 + index, value, 0xF7]))

	def SendSlider(self, index, value):
		self.sendRawMsg(bytearray([0xF0, 0xE0 + index] + list(value.to_bytes(2, sys.byteorder)) +  [0xF7]))

	def SendEncoder(self, index, values):
		left[:] = ['1' if v else '0' for v in values][:7]
		right[:] = ['1' if v else '0' for v in values][7:]
		print('left', left)
		print('right', right)
		self.sendRawMsg(bytearray([0xF0, 0xB0, 48 + index, int(left, 2), 0xF7]))
		self.sendRawMsg(bytearray([0xF0, 0xB0, 56 + index, int(right, 2), 0xF7]))

	def SendScribble(self, index, topText, bottomText, color, bottomInverted):
		self.sendRawMsg(bytearray([0xF0, 0x00, 0x00, 0x66, 0x58, 0x20 + index, (0x00 if not bottomInverted else 0x40) + color]
			+ list(bytearray(topText.ljust(7, '\0'), 'utf-8')) + list(bytearray(bottomText.ljust(7, '\0'), 'utf-8')) + [0xF7]))

	def SendMeter(self, index, level):
		self.sendRawMsg(bytearray([0xF0, 0xD0, 0x00, index + level, 0xF7]))

	def SendKeepAlive(self):
		if self.running:
			self.sendRawMsg([0xF0, 0x00, 0x00, 0x66, 0x14, 0x00, 0xF7])
			threading.Timer(6, self.SendKeepAlive).start()

	def HandleMsg(self, data):
		self.lastMsg = datetime.now()
		#Keep alive message
		if data == bytearray([0xF0, 0x00, 0x20, 0x32, 0x58, 0x54, 0x00, 0xF7]):
			return
		#Confirmation message
		if data == bytearray([0xF0, 0x00, 0x00, 0x66, 0x58, 0x01, 0x30, 0x31, 0x35, 0x36, 0x34, 0x30, 0x37, 0x44, 0x37, 0x37, 0x39, 0xF7]):
			return

		#print('Length: ', len(data))
		if data[0] == 0x90:
			self.buttons.buttons[int(data[1])].pressed = int(data[2]) == 127
			if self.onButtonChange:
				self.onButtonChange(self.buttons.buttons[int(data[1])])
		elif data[0] >= 0xE0 and data[0] <= 0xE8:
			print('Fader: (' + str(int(data[0] - 0xE0)) + ', ' + str(data[2] << 8 | data[1]) + ')')
			if self.onSliderChange:
				self.onSliderChange(int(data[0] - 0xE0), int(data[2] << 8 | data[1]))
		elif data[0] == 0xB0:
			if self.onEncoderChange:
				self.onEncoderChange(int(data[1] - 0x10), int(0x40 - data[2]) if data[2] > 0x40 else data[2])
			print('Encoder: (' + str(int(data[1] - 0x10)) + ', ' + str(int(-(data[2] - 0x40) if data[2] > 0x40 else data[2])) + ')')
		elif data[0] == 0xF0:
			print('System: ', [hex(d) for d in data])
		else:
			print('Unknown: ', [hex(d) for d in data])

	def GetButton(self, name: str):
		return self.buttons.GetButton(name)


	class Channel:
		class Color(Enum):
			Off = 0
			Red = 1
			Green = 2
			Yellow = 2
			Blue = 4
			Pink = 5
			Cyan = 6
			White = 7

		def __init__(self, parent, index):
			self.xtouch = parent
			self.index = index

			# Scribble variables
			self.scribbleTopText = ''
			self.scribbleBottomText = ''
			self.scribbleColor = self.Color.White
			self.bottomInverted = False

			# Slider value
			self.slider = 0

			# Encoder values
			self.encoderValue = 0
			self.encoderFromCenter = True
			self.encoderBetween = False

			# Meter values
			self.meterDecay = True
			self.meterLevel = 0

		def SetAll(self):
			self.SendSlider()
			self.SendEncoder()
			self.SendScribble()

		#
		# Slider
		#
		def SetSlider(self, value):
			self.sliderValue = value
			self.SendSlider()

		def SendSlider(self):
			self.xtouch.SendSlider(self.index, self.sliderValue)

		#
		# Encoder Lights
		#
		def SetEncoderValue(self, value):
			# This value goes from -6 to 6 (including floats)
			self.encoderValue = value
			self.SendEncoder()

		def SetEncoderFromCenter(self, fromCenter: bool):
			self.encoderFromCenter = fromCenter
			self.SendEncoder()

		def SetEncoderBetween(self, between: bool):
			self.encoderBetween = between
			self.SendEncoder()

		def SendEncoder(self):
			enc = self.encoderValue
			if self.encoderFromCenter:
				self.xtouch.SendEncoder(self.index, [enc <= -6, enc <= -5, enc <= -4, enc <= -3, enc <= -2, enc <= -1, True, enc >= 1, enc >= 2, enc >= 3, enc >= 4, enc >= 5, enc >= 6])
			elif self.encoderBetween:
				self.xtouch.SendEncoder(self.index, [enc <= -5.25, enc >= -5.75 and enc <= -4.25, enc >= -4.75 and enc <= -3.25, enc >= -3.75 and enc <= -2.25, enc >= -2.75 and enc <= -1.25, enc >= -1.75 and enc <= -0.25, enc >= -0.75 and enc <= 0.75, enc >= 0.25 and enc <= 1.75, enc >= 1.25 and enc <= 2.75, enc >= 2.25 and enc <= 3.75, enc >= 3.25 and enc <= 4.75, enc >= 4.25 and enc <= 5.75, enc >= 5.25])
			else:
				self.xtouch.SendEncoder(self.index, [enc < -5.5, enc >= -5.5 and enc < -4.5, enc >= -4.5 and enc < -3.5, enc >= -3.5 and enc < -2.5, enc >= -2.5 and enc < -1.5, enc >= -1.5 and enc < -0.5, enc >= -0.5 and enc < 0.5, enc >= 0.5 and enc < 1.5, enc >= 1.5 and enc < 2.5, enc >= 2.5 and enc < 3.5, enc >= 3.5 and enc < 4.5, enc >= 4.5 and enc < 5.5, enc >= 5.5])

		#
		# Scribble Strip
		#
		def SetScribble(self, topText: str, bottomText: str, color: Color, bottomInverted: bool):
			self.scribbleTopText = topText
			self.scribbleBottomText = bottomText
			self.scribbleColor = color
			self.bottomInverted = bottomInverted
			self.SendScribble()

		def SetScribbleText(self, topText: str, bottomText: str):
			self.scribbleTopText = topText
			self.scribbleBottomText = bottomText
			self.SendScribble()

		def SetScribbleTopText(self, topText: str):
			self.scribbleTopText = topText
			self.SendScribble()

		def SetScribbleBottomText(self, bottomText: str):
			self.scribbleBottomText = bottomText
			self.SendScribble()

		def SetScribbleColor(self, color: Color):
			self.scribbleColor = color
			self.SendScribble()

		def SetScribbleInverted(self, bottomInverted: bool):
			self.bottomInverted = bottomInverted
			self.SendScribble()

		def SendScribble(self):
			self.xtouch.SendScribble(self.index, self.scribbleTopText, self.scribbleBottomText, self.scribbleColor, self.bottomInverted)


		#
		# Meters
		#
		def SetMeterLevel(self, level: int):
			if level < 0:
				level = 0
			if level > 8:
				level = 8
			self.meterLevel = level
			self.SendMeter()

		def SetMeterDecay(self, decay: bool):
			self.meterDecay = decay
			self.SendMeter()

		def SendMeter(self):
			self.xtouch.SendMeter(self.index * 2, self.meterLevel)

	class Buttons:
		_buttonList = [
			'Ch1Rec',
			'Ch2Rec',
			'Ch3Rec',
			'Ch4Rec',
			'Ch5Rec',
			'Ch6Rec',
			'Ch7Rec',
			'Ch8Rec',

			'Ch1Solo',
			'Ch2Solo',
			'Ch3Solo',
			'Ch4Solo',
			'Ch5Solo',
			'Ch6Solo',
			'Ch7Solo',
			'Ch8Solo',

			'Ch1Mute',
			'Ch2Mute',
			'Ch3Mute',
			'Ch4Mute',
			'Ch5Mute',
			'Ch6Mute',
			'Ch7Mute',
			'Ch8Mute',

			'Ch1Sel',
			'Ch2Sel',
			'Ch3Sel',
			'Ch4Sel',
			'Ch5Sel',
			'Ch6Sel',
			'Ch7Sel',
			'Ch8Sel',

			'Ch1Enc',
			'Ch2Enc',
			'Ch3Enc',
			'Ch4Enc',
			'Ch5Enc',
			'Ch6Enc',
			'Ch7Enc',
			'Ch8Enc',

			'Track',
			'Send',
			'PanSurr',
			'PlugIn',
			'EQ',
			'Inst',

			'BankLeft',
			'BankRight',
			'ChannelLeft',
			'ChannelRight',

			'Flip',
			'Global',

			'Name/Value',
			'Beats',

			'F1',
			'F2',
			'F3',
			'F4',
			'F5',
			'F6',
			'F7',
			'F8',

			'MIDITracks',
			'Inputs',
			'AudioTracks',
			'AudioInst',
			'Aux',
			'Buses',
			'Outputs',
			'User',

			'Shift',
			'Option',
			'Control',
			'Alt',

			'Read',
			'Write',
			'Trim',
			'Touch',
			'Latch',
			'Group',

			'Save',
			'Undo',
			'Cancel',
			'Enter',

			'Marker',
			'Nudge',
			'Cycle',
			'Drop',
			'Replace',
			'Click',
			'Solo',

			'Rewind',
			'FastForward',
			'Stop',
			'Play',
			'Record',

			'Up',
			'Down',
			'Left',
			'Right',
			'Zoom',
			'Scrub',

			'_',
			'_',

			'Ch1Touch',
			'Ch2Touch',
			'Ch3Touch',
			'Ch4Touch',
			'Ch5Touch',
			'Ch6Touch',
			'Ch7Touch',
			'Ch8Touch',
			'MainTouch',

			'SMPTELED',
			'BeatsLED',
			'SoloLED'
		]

		class LEDState(Enum):
			Off = 0
			Blinking = 1
			On = 127

		class Button():
			def __init__(self, parent, index):
				self.parent = parent
				self.index = index
				self._pressed = False
				self.onChange = None
				self.onDown = None
				self.onUp = None
				self.state = self.parent.LEDState.Off

			def setOnChange(self, callback):
				self.onChange = callback

			def setOnDown(self, callback):
				self.onDown = callback

			def setOnUp(self, callback):
				self.onUp = callback

			@property
			def name(self):
				return self.parent._buttonList[self.index]

			@property
			def pressed(self):
				return self._pressed

			@pressed.setter
			def pressed(self, value):
				if value != self._pressed:
					if self.onChange:
						self.onChange(self)

					if value and self.onDown:
						self.onDown(self)

					if not value and self.onUp:
						self.onUp(self)

				self._pressed = value

			def SendLED(self):
				self.parent.xtouch.SendButton(self.index, self.state.value)

			def SetLED(self, state: bool):#: LEDState):
				self.state = self.parent.LEDState.On if state else self.parent.LEDState.Off
				self.SendLED()

			def BlinkLED(self):
				self.state = self.parent.LEDState.Blinking
				self.SendLED()

		def __init__(self, parent):
			self.xtouch = parent
			self.buttons = []

			for i in range(len(self._buttonList)):
				self.buttons.append(self.Button(self, i))

		def SetAllLEDs(self, state: LEDState):
			for b in self.buttons:
				b.SetLED(state)

		def GetButton(self, name: str):
			return self.buttons[self._buttonList.index(name)]

xtouch = XTouch('192.168.60.114')

def PrintButton(button):
	print('%s (%d) %s' % (button.name, button.index, 'pressed' if button.pressed else 'released'))
	button.SetLED(button.pressed)

def PrintFlip(button):
	print('FLIP %s' % ('PRESSED' if button.pressed else 'RELEASED'))

def FlipPress(button):
	print('PRESSED FLIP')

def FlipRelease(button):
	print('RELEASED FLIP')

xtouch.setOnButtonChange(PrintButton)
xtouch.GetButton('Flip').setOnChange(PrintFlip)
xtouch.GetButton('Flip').setOnDown(FlipPress)
xtouch.GetButton('Flip').setOnUp(FlipRelease)

def SetAllSliders(index, value):
	xtouch.SendScribble(index, '', '', 5, False)
	for i in range(9):
		if i != index:
			xtouch.SendSlider(i, value)
			xtouch.SendScribble(i, '', '', 7, False)

xtouch.setOnSliderChange(SetAllSliders)

xtouch.channels[0].SetMeterLevel(8)

input("Press enter...")
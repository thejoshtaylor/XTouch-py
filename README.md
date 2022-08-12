# XTouch-py

A complete XCtrl interface for the Behringer XTouch Control Surface that works over UDP.

## Example

```python
import XTouch

xtouch = XTouch()
xtouch.waitToConnect()

xtouch.channel[0].SetSlider(8192)
```

## Features

* Full Mackie-like Control
 * Slider I/O
  * Get/set slider position
  * Get xlider touch sensor
 * Button I/O
 * Encoder input
 * Meters
* Color scribble strips
* Timecode display control
* Network discovery

This library is capable of full control of the XTouch over LAN using UDP. It extends upon features available in the Mackie Control Universal Protocol to give you more control over you XTouch.
There is an option built into the library to allow for multiple objects to be used for the same XTouch. This allows for having multiple "modes" that the XTouch can be in.

## Setup

The XTouch must be put into XCtrl mode and must be on the same network as the device controlling the XTouch. Set the XTouch to DHCP and you can discover it with the library.

### XCtrl Protocol

I had to do a little bit of my own digging, but [this guide](http://www.budgetfeatures.com/XctlDOC/Xctl%20Protocol%20for%20X-Touch%20V1.0.pdf) by FK was incredibly useful and got me most of the way. The protocol is very similar to the Mackie Control Universal protocol, but it has a few extra caveats.
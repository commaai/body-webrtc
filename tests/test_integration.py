#!/usr/bin/env python3

import asyncio
import unittest

import aiortc
from aiortc.mediastreams import AudioStreamTrack, VideoStreamTrack
from parameterized import parameterized

from teleoprtc.builder import WebRTCOfferBuilder, WebRTCAnswerBuilder
from teleoprtc.stream import StreamingOffer
from teleoprtc.info import parse_info_from_offer


class SimpleAnswerProvider:
  def __init__(self):
    self.stream = None

  async def __call__(self, offer: StreamingOffer):
    assert self.stream is None, "This may only be called once"

    info = parse_info_from_offer(offer.sdp)

    builder = WebRTCAnswerBuilder(offer.sdp)
    for cam in offer.video:
      builder.add_video_stream(cam, VideoStreamTrack())
    if info.expected_audio_track:
      builder.add_audio_stream(AudioStreamTrack())
    if info.incoming_audio_track:
      builder.offer_to_receive_audio_stream()

    self.stream = builder.stream()
    answer = await self.stream.start()

    return answer
  
class TestStreamIntegration(unittest.IsolatedAsyncioTestCase):
  @parameterized.expand([
    # name, recv_cameras, recv_audio, messaging
    ("multi_camera", ["driver", "wideRoad", "road"], False, False),
    ("camera_and_audio", ["driver"], True, False),
    ("camera_and__messaging", ["driver"], False, True),
    ("camera_and_audio_and_messaging", ["driver", "wideRoad", "road"], True, True),
  ])
  async def test_multi_camera(self, name, cameras, recv_audio, add_messaging):
    simple_answerer = SimpleAnswerProvider()
    offer_builder = WebRTCOfferBuilder(simple_answerer)
    for cam in cameras:
      offer_builder.offer_to_receive_video_stream(cam)
    if recv_audio:
      offer_builder.offer_to_receive_audio_stream()
    if add_messaging:
      offer_builder.add_messaging()
    stream = offer_builder.stream()

    offer = await stream.start()
    self.assertTrue(stream.is_started)

    try:
      async with asyncio.timeout(2):
        await stream.wait_for_connection()
    except asyncio.TimeoutError as e:
      self.fail("Timed out waiting for connection")
    self.assertTrue(stream.is_connected_and_ready)

    self.assertEqual(stream.has_messaging_channel(), add_messaging)
    if stream.has_messaging_channel():
      channel = stream.get_messaging_channel()
      self.assertIsNotNone(channel)
      self.assertEqual(channel.readyState, "open")
  
    self.assertEqual(stream.has_incoming_audio_track(), recv_audio)
    if stream.has_incoming_audio_track():
      track = stream.get_incoming_audio_track(False)
      self.assertIsNotNone(track)
      self.assertEqual(track.readyState, "live")
      self.assertEqual(track.kind, "audio")
      # test audio recv
      try:
        async with asyncio.timeout(1):
          await track.recv()
      except asyncio.TimeoutError as e:
        self.fail("Timed out waiting for audio frame")

    for cam in cameras:
      self.assertTrue(stream.has_incoming_video_track(cam))
      if stream.has_incoming_video_track(cam):
        track = stream.get_incoming_video_track(cam, False)
        self.assertIsNotNone(track)
        self.assertEqual(track.readyState, "live")
        self.assertEqual(track.kind, "video")
        # test video recv
        try:
          async with asyncio.timeout(1):
            await stream.get_incoming_video_track(cam, False).recv()
        except asyncio.TimeoutError as e:
          self.fail("Timed out waiting for video frame")

    await stream.stop()
    await simple_answerer.stream.stop()
    self.assertFalse(stream.is_started)
    self.assertFalse(stream.is_connected_and_ready)


if __name__ == '__main__':
  unittest.main()   

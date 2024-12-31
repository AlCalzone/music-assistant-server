"""
DEMO/TEMPLATE Player Provider for Music Assistant.

This is an empty player provider with no actual implementation.
Its meant to get started developing a new player provider for Music Assistant.

Use it as a reference to discover what methods exists and what they should return.
Also it is good to look at existing player providers to get a better understanding,
due to the fact that providers may be flexible and support different features and/or
ways to discover players on the network.

In general, the actual device communication should reside in a separate library.
You can then reference your library in the manifest in the requirements section,
which is a list of (versioned!) python modules (pip syntax) that should be installed
when the provider is selected by the user.

To add a new player provider to Music Assistant, you need to create a new folder
in the providers folder with the name of your provider (e.g. 'my_player_provider').
In that folder you should create (at least) a __init__.py file and a manifest.json file.

Optional is an icon.svg file that will be used as the icon for the provider in the UI,
but we also support that you specify a material design icon in the manifest.json file.

IMPORTANT NOTE:
We strongly recommend developing on either MacOS or Linux and start your development
environment by running the setup.sh scripts in the scripts folder of the repository.
This will create a virtual environment and install all dependencies needed for development.
See also our general DEVELOPMENT.md guide in the repository for more information.

"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TYPE_CHECKING

from aiohttp import web
from music_assistant_models.enums import (
    ContentType,
    PlayerFeature,
    PlayerState,
    PlayerType,
    ProviderFeature,
)
from music_assistant_models.media_items import AudioFormat
from music_assistant_models.player import DeviceInfo, Player, PlayerMedia

from music_assistant.constants import (
    CONF_ENTRY_CROSSFADE,
    CONF_ENTRY_FLOW_MODE,
)
from music_assistant.helpers.ffmpeg import get_ffmpeg_stream
from music_assistant.helpers.util import empty_queue
from music_assistant.models.player_provider import PlayerProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import (
        ConfigEntry,
        ConfigValueType,
        PlayerConfig,
        ProviderConfig,
    )
    from music_assistant_models.provider import ProviderManifest

    from music_assistant import MusicAssistant
    from music_assistant.models import ProviderInstanceType

CBR_OGG_OPUS_FORMAT = AudioFormat(
    content_type=ContentType.OPUS, channels=2, sample_rate=48000, bit_rate=96000
)

MP3 = AudioFormat(
    content_type=ContentType.MP3,
)


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    # setup is called when the user wants to setup a new provider instance.
    # you are free to do any preflight checks here and but you must return
    #  an instance of the provider.
    return TeddyCloudPlayerProvider(mass, manifest, config)


async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """
    Return Config entries to setup this provider.

    instance_id: id of an existing provider instance (None if new instance setup).
    action: [optional] action key called from config entries UI.
    values: the (intermediate) raw values for config entries sent with the action.
    """
    # ruff: noqa: ARG001
    # Config Entries are used to configure the Player Provider if needed.
    # See the models of ConfigEntry and ConfigValueType for more information what is supported.
    # The ConfigEntry is a dataclass that represents a single configuration entry.
    # The ConfigValueType is an Enum that represents the type of value that
    # can be stored in a ConfigEntry.
    # If your provider does not need any configuration, you can return an empty tuple.
    return ()


# class TeddyCloudHttpHandler(BaseHTTPRequestHandler):
#     _logger: Logger = logging.getLogger("TeddyCloudHttpHandler")
#     upstream_url: str = ""

#     async def forward_request(self):
#         headers = {key: value for key, value in self.headers.items()}
#         sent_status = False
#         async with ClientSession() as session:
#             while True:
#                 self._logger.debug("x")
#                 self._logger.debug("Now streaming %s", self.upstream_url)
#                 self._logger.debug("x")
#                 current_url = self.upstream_url
#                 async with session.get(self.upstream_url, headers=headers) as response:
#                     if not sent_status:
#                         self.send_response(response.status)
#                         # for key, value in response.headers.items():
#                         #     self._logger.debug("Header: %s: %s", key, value)
#                         #     self.send_header(key, value)
#                         self.end_headers()
#                         sent_status = True
#                     async for chunk in response.content.iter_chunked(4096):
#                         self.wfile.write(chunk)
#                         # When the current URL has changed, continue with the new URL
#                         if current_url != self.upstream_url:
#                             self._logger.debug("URL changed, breaking")
#                             break

#     def do_GET(self):
#         self._logger.debug(
#             "GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers)
#         )
#         self._logger.debug("Upstream URL: %s", self.upstream_url)
#         asyncio.run(self.forward_request())


class TeddyCloudPlayerProvider(PlayerProvider):
    """
    Example/demo Player provider.

    Note that this is always subclassed from PlayerProvider,
    which in turn is a subclass of the generic Provider model.

    The base implementation already takes care of some convenience methods,
    such as the mass object and the logger. Take a look at the base class
    for more information on what is available.

    Just like with any other subclass, make sure that if you override
    any of the default methods (such as __init__), you call the super() method.
    In most cases its not needed to override any of the builtin methods and you only
    implement the abc methods with your actual implementation.
    """

    # _my_handler: TeddyCloudHttpHandler
    # _my_server: HTTPServer
    # _my_thread: Thread

    audio_source: AsyncGenerator[bytes, None] | None = None
    audio_source_changed: bool = False
    stopping: bool = False
    task: asyncio.Task | None = None
    subscribers: list[asyncio.Queue] = []

    # def start_my_server(self):
    #     server_address = ("", 9998)
    #     self.logger.debug("Starting TeddyCloud proxy server on %s", server_address)
    #     _my_handler = TeddyCloudHttpHandler
    #     _my_server = HTTPServer(server_address, _my_handler)
    #     _my_thread = Thread(target=_my_server.serve_forever)
    #     _my_thread.daemon = True
    #     _my_thread.start()
    #     self._my_handler = _my_handler
    #     self._my_server = _my_server
    #     self._my_thread = _my_thread

    # def stop_my_server(self):
    #     self._my_server.shutdown()
    #     self._my_thread.join()

    @property
    def supported_features(self) -> set[ProviderFeature]:
        """Return the features supported by this Provider."""
        # MANDATORY
        # you should return a tuple of provider-level features
        # here that your player provider supports or an empty tuple if none.
        # for example 'ProviderFeature.SYNC_PLAYERS' if you can sync players.
        return ()

    async def loaded_in_mass(self) -> None:
        """Call after the provider has been loaded."""
        # OPTIONAL
        # this is an optional method that you can implement if
        # relevant or leave out completely if not needed.
        # it will be called after the provider has been fully loaded into Music Assistant.
        # you can use this for instance to trigger custom (non-mdns) discovery of players
        # or any other logic that needs to run after the provider is fully loaded.
        await super().loaded_in_mass()

        # FIXME: Determine the id from the teddycloud instance
        player_id = "my_teddycloud"
        player = self.mass.players.get(player_id, raise_unavailable=False)
        if not player:
            # address = "https://tdcld.lan"
            player = Player(
                player_id=player_id,
                provider=self.instance_id,
                type=PlayerType.PLAYER,
                name="TeddyCloud",
                available=True,
                powered=True,
                device_info=DeviceInfo(
                    # model=self._fully.deviceInfo["deviceModel"],
                    # manufacturer=self._fully.deviceInfo["deviceManufacturer"],
                    # ip_address=address,
                ),
                supported_features={
                    PlayerFeature.UNKNOWN,
                },
                needs_poll=True,
                poll_interval=10,
            )
        await self.mass.players.register_or_update(player)
        self._handle_player_update()

        self.mass.streams.register_dynamic_route("/teddycloud/stream", self._serve_stream)
        self.logger.debug(
            f"Teddycloud stream available at {self.mass.streams.base_url}/teddycloud/stream"
        )

    def _start_stream(self) -> None:
        self.task = asyncio.create_task(self._proxy_stream())

    async def _stop_stream(self) -> None:
        """Stop/cancel the stream."""
        if self.task.done():
            return
        self.stopping = True
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        self.task = None

    async def _proxy_stream(self) -> None:
        """Run the stream for the given audio source."""
        # expected_clients = self.expected_clients or 1
        # # wait for first/all subscriber
        # count = 0
        # while count < 50:
        #     await asyncio.sleep(0.1)
        #     count += 1
        #     if len(self.subscribers) >= expected_clients:
        #         break
        # LOGGER.debug(
        #     "Starting multi-client stream with %s/%s clients",
        #     len(self.subscribers),
        #     self.expected_clients,
        # )

        while not self.stopping:
            self.audio_source_changed = False
            while not self.audio_source:
                await asyncio.sleep(0.1)
            async for chunk in self.audio_source:
                try:
                    await asyncio.gather(
                        *[sub.put(chunk) for sub in self.subscribers], return_exceptions=True
                    )
                except (BrokenPipeError, ConnectionResetError, ConnectionError):
                    # race condition
                    break
                if self.stopping or self.audio_source_changed:
                    break
        self.stopping = False

        # async for chunk in self.audio_source:
        #     # fail_count = 0
        #     # while len(self.subscribers) == 0:
        #     #     await asyncio.sleep(0.1)
        #     #     fail_count += 1
        #     #     if fail_count > 50:
        #     #         # LOGGER.warning("No clients connected, stopping stream")
        #     #         return
        #     await asyncio.gather(
        #         *[sub.put(chunk) for sub in self.subscribers], return_exceptions=True
        #     )
        # EOF: send empty chunk
        await asyncio.gather(*[sub.put(b"") for sub in self.subscribers], return_exceptions=True)

    async def _serve_stream(self, request: web.Request) -> web.Response:
        """Serve the multi-client flow stream audio to a player."""
        # player_id = request.query.get("player_id")
        # FIXME: Determine the id from the teddycloud instance
        player_id = "my_teddycloud"
        self.logger.debug("connection from %s", request.remote)

        if not self.mass.players.get(player_id):
            raise web.HTTPNotFound(reason=f"Unknown player: {player_id}")

        if not self.audio_source:
            raise web.HTTPNotFound(reason="No audio source set up!")

        # if not (stream := self._multi_streams.get(player_id, None)) or stream.done:
        #     raise web.HTTPNotFound(f"There is no active stream for {player_id}!")

        resp = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                # "Content-Type": "audio/ogg; codecs=opus",
                "Content-Type": "audio/mpeg",
            },
        )
        await resp.prepare(request)

        # return early if this is not a GET request
        if request.method != "GET":
            return resp

        # all checks passed, start streaming!
        self.logger.info("streaming audio to %s", player_id)

        async for chunk in self._subscribe_raw():
            try:
                await resp.write(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionError):
                # race condition
                break

        self.logger.info("stream for %s ended", player_id)

        return resp

    async def _subscribe_raw(self) -> AsyncGenerator[bytes, None]:
        """Subscribe to the raw/unaltered audio stream."""
        try:
            queue = asyncio.Queue(2)
            self.subscribers.append(queue)
            self._handle_player_update()
            while True:
                chunk = await queue.get()
                if chunk == b"":
                    break
                yield chunk
        finally:
            with suppress(ValueError):
                self.subscribers.remove(queue)
            self._handle_player_update()

    def _handle_player_update(self) -> None:
        """Update TeddyCloud player attributes."""
        # FIXME: Determine the id from the teddycloud instance
        player_id = "my_teddycloud"
        if not (player := self.mass.players.get(player_id)):
            return
        # player.name = self._fully.deviceInfo["deviceName"]
        # player.volume_level = snap_client.volume
        # for volume_dict in self._fully.deviceInfo.get("audioVolumes", []):
        #     if str(AUDIOMANAGER_STREAM_MUSIC) in volume_dict:
        #         volume = volume_dict[str(AUDIOMANAGER_STREAM_MUSIC)]
        #         player.volume_level = volume
        #         break
        # current_url = self._fully.deviceInfo.get("soundUrlPlaying")
        # player.current_item_id = current_url
        # if not current_url:
        #     player.state = PlayerState.IDLE
        if not self.audio_source:
            player.state = PlayerState.IDLE
        elif len(self.subscribers) == 0:
            player.state = PlayerState.PAUSED
        else:
            player.state = PlayerState.PLAYING

        player.available = True
        self.mass.players.update(player_id)

    async def unload(self) -> None:
        """
        Handle unload/close of the provider.

        Called when provider is deregistered (e.g. MA exiting or config reloading).
        """
        # OPTIONAL
        # this is an optional method that you can implement if
        # relevant or leave out completely if not needed.
        # it will be called when the provider is unloaded from Music Assistant.
        # this means also when the provider is getting reloaded
        await self._stop_stream()
        for sub_queue in list(self.subscribers):
            empty_queue(sub_queue)

        self.audio_source = None
        self.audio_source_changed = False

    # async def on_mdns_service_state_change(
    #     self, name: str, state_change: ServiceStateChange, info: AsyncServiceInfo | None
    # ) -> None:
    #     """Handle MDNS service state callback."""
    #     # MANDATORY IF YOU WANT TO USE MDNS DISCOVERY
    #     # OPTIONAL if you dont use mdns for discovery of players
    #     # If you specify a mdns service type in the manifest.json, this method will be called
    #     # automatically on mdns changes for the specified service type.

    #     # If no mdns service type is specified, this method is omitted and you
    #     # can completely remove it from your provider implementation.

    #     # NOTE: If you do not use mdns for discovery of players on the network,
    #     # you must implement your own discovery mechanism and logic to add new players
    #     # and update them on state changes when needed.
    #     # Below is a bit of example implementation but we advise to look at existing
    #     # player providers for more inspiration.
    #     name = name.split("@", 1)[1] if "@" in name else name
    #     player_id = info.decoded_properties["uuid"]  # this is just an example!
    #     # handle removed player
    #     if state_change == ServiceStateChange.Removed:
    #         # check if the player manager has an existing entry for this player
    #         if mass_player := self.mass.players.get(player_id):
    #             # the player has become unavailable
    #             self.logger.debug("Player offline: %s", mass_player.display_name)
    #             mass_player.available = False
    #             self.mass.players.update(player_id)
    #         return
    #     # handle update for existing device
    #     # (state change is either updated or added)
    #     # check if we have an existing player in the player manager
    #     # note that you can use this point to update the player connection info
    #     # if that changed (e.g. ip address)
    #     if mass_player := self.mass.players.get(player_id):
    #         # existing player found in the player manager,
    #         # this is an existing player that has been updated/reconnected
    #         # or simply a re-announcement on mdns.
    #         cur_address = get_primary_ip_address_from_zeroconf(info)
    #         if cur_address and cur_address != mass_player.device_info.address:
    #             self.logger.debug(
    #                 "Address updated to %s for player %s", cur_address, mass_player.display_name
    #             )
    #             mass_player.device_info = DeviceInfo(
    #                 model=mass_player.device_info.model,
    #                 manufacturer=mass_player.device_info.manufacturer,
    #                 address=str(cur_address),
    #             )
    #         if not mass_player.available:
    #             # if the player was marked offline and you now receive an mdns update
    #             # it means the player is back online and we should try to connect to it
    #             self.logger.debug("Player back online: %s", mass_player.display_name)
    #             # you can try to connect to the player here if needed
    #             mass_player.available = True
    #         # inform the player manager of any changes to the player object
    #         # note that you would normally call this from some other callback from
    #         # the player's native api/library which informs you of changes in the player state.
    #         # as a last resort you can also choose to let the player manager
    #         # poll the player for state changes
    #         self.mass.players.update(player_id)
    #         return
    #     # handle new player
    #     self.logger.debug("Discovered device %s on %s", name, cur_address)
    #     # your own connection logic will probably be implemented here where
    #     # you connect to the player etc. using your device/provider specific library.

    #     # Instantiate the MA Player object and register it with the player manager
    #     mass_player = Player(
    #         player_id=player_id,
    #         provider=self.instance_id,
    #         type=PlayerType.PLAYER,
    #         name=name,
    #         available=True,
    #         powered=False,
    #         device_info=DeviceInfo(
    #             model="Model XYX",
    #             manufacturer="Super Brand",
    #             ip_address=cur_address,
    #         ),
    #         # set the supported features for this player only with
    #         # the ones the player actually supports
    #         supported_features={
    #             PlayerFeature.POWER,  # if the player can be turned on/off
    #             PlayerFeature.VOLUME_SET,
    #             PlayerFeature.VOLUME_MUTE,
    #             PlayerFeature.PLAY_ANNOUNCEMENT,  # see play_announcement method
    #         },
    #     )
    #     # register the player with the player manager
    #     await self.mass.players.register(mass_player)

    #     # once the player is registered, you can either instruct the player manager to
    #     # poll the player for state changes or you can implement your own logic to
    #     # listen for state changes from the player and update the player object accordingly.
    #     # in any case, you need to call the update method on the player manager:
    #     self.mass.players.update(player_id)

    async def get_player_config_entries(self, player_id: str) -> tuple[ConfigEntry, ...]:
        """Return all (provider/player specific) Config Entries for the given player (if any)."""
        # OPTIONAL
        # this method is optional and should be implemented if you need player specific
        # configuration entries. If you do not need player specific configuration entries,
        # you can leave this method out completely to accept the default implementation.
        # Please note that you need to call the super() method to get the default entries.
        base_entries = await super().get_player_config_entries(player_id)
        return (
            *base_entries,
            CONF_ENTRY_FLOW_MODE,
            CONF_ENTRY_CROSSFADE,
        )

    async def on_player_config_change(self, config: PlayerConfig, changed_keys: set[str]) -> None:
        """Call (by config manager) when the configuration of a player changes."""
        # OPTIONAL
        # this will be called whenever a player config changes
        # you can use this to react to changes in player configuration
        # but this is completely optional and you can leave it out if not needed.

    async def cmd_stop(self, player_id: str) -> None:
        """Send STOP command to given player."""
        # MANDATORY
        # this method is mandatory and should be implemented.
        # this method should send a stop command to the given player.

    async def cmd_play(self, player_id: str) -> None:
        """Send PLAY command to given player."""
        # MANDATORY
        # this method is mandatory and should be implemented.
        # this method should send a play command to the given player.

    async def cmd_pause(self, player_id: str) -> None:
        """Send PAUSE command to given player."""
        # OPTIONAL - required only if you specified PlayerFeature.PAUSE
        # this method should send a pause command to the given player.

    async def cmd_volume_set(self, player_id: str, volume_level: int) -> None:
        """Send VOLUME_SET command to given player."""
        # OPTIONAL - required only if you specified PlayerFeature.VOLUME_SET
        # this method should send a volume set command to the given player.

    async def cmd_volume_mute(self, player_id: str, muted: bool) -> None:
        """Send VOLUME MUTE command to given player."""
        # OPTIONAL - required only if you specified PlayerFeature.VOLUME_MUTE
        # this method should send a volume mute command to the given player.

    async def cmd_seek(self, player_id: str, position: int) -> None:
        """Handle SEEK command for given queue.

        - player_id: player_id of the player to handle the command.
        - position: position in seconds to seek to in the current playing item.
        """
        # OPTIONAL - required only if you specified PlayerFeature.SEEK
        # this method should handle the seek command for the given player.
        # the position is the position in seconds to seek to in the current playing item.

    async def play_media(
        self,
        player_id: str,
        media: PlayerMedia,
    ) -> None:
        """Handle PLAY MEDIA on given player.

        This is called by the Players controller to start playing a mediaitem on the given player.
        The provider's own implementation should work out how to handle this request.

            - player_id: player_id of the player to handle the command.
            - media: Details of the item that needs to be played on the player.
        """
        # MANDATORY
        # this method is mandatory and should be implemented.
        # this method should handle the play_media command for the given player.
        # It will be called when media needs to be played on the player.
        # The media object contains all the details needed to play the item.

        # In 99% of the cases this will be called by the Queue controller to play
        # a single item from the queue on the player and the uri within the media
        # object will then contain the URL to play that single queue item.

        # If your player provider does not support enqueuing of items,
        # the queue controller will simply call this play_media method for
        # each item in the queue to play them one by one.

        # In order to support true gapless and/or crossfade, we offer the option of
        # 'flow_mode' playback. In that case the queue controller will stitch together
        # all songs in the playback queue into a single stream and send that to the player.
        # In that case the URI (and metadata) received here is that of the 'flow mode' stream.

        # Examples of player providers that use flow mode for playback by default are Airplay,
        # SnapCast and Fully Kiosk.

        # Examples of player providers that optionally use 'flow mode' are Google Cast and
        # Home Assistant. They provide a config entry to enable flow mode playback.

        # Examples of player providers that natively support enqueuing of items are Sonos,
        # Slimproto and Google Cast.
        self.audio_source = get_ffmpeg_stream(
            audio_input=media.uri,
            input_format=AudioFormat(content_type=ContentType.try_parse(media.uri)),
            output_format=MP3,
            # TeddyCloud has its own transcoder which would read too much of the stream
            # if we don't limit the readrate. This would cause long delays when skipping
            # tracks etc.
            extra_input_args=["-re"],
        )
        self.audio_source_changed = True
        self.logger.debug("Set up audio source to %s", media.uri)

        if not self.task:
            self._start_stream()
        self._handle_player_update()

        return ()

    async def enqueue_next_media(self, player_id: str, media: PlayerMedia) -> None:
        """
        Handle enqueuing of the next (queue) item on the player.

        Called when player reports it started buffering a queue item
        and when the queue items updated.

        A PlayerProvider implementation is in itself responsible for handling this
        so that the queue items keep playing until its empty or the player stopped.

        This will NOT be called if the end of the queue is reached (and repeat disabled).
        This will NOT be called if the player is using flow mode to playback the queue.
        """
        # this method should handle the enqueuing of the next queue item on the player.

    async def cmd_group(self, player_id: str, target_player: str) -> None:
        """Handle GROUP command for given player.

        Join/add the given player(id) to the given (master) player/sync group.

            - player_id: player_id of the player to handle the command.
            - target_player: player_id of the syncgroup master or group player.
        """
        # OPTIONAL - required only if you specified ProviderFeature.SYNC_PLAYERS
        # this method should handle the sync command for the given player.
        # you should join the given player to the target_player/syncgroup.

    async def cmd_ungroup(self, player_id: str) -> None:
        """Handle UNGROUP command for given player.

        Remove the given player from any (sync)groups it currently is grouped to.

            - player_id: player_id of the player to handle the command.
        """

    async def play_announcement(
        self, player_id: str, announcement: PlayerMedia, volume_level: int | None = None
    ) -> None:
        """Handle (provider native) playback of an announcement on given player."""
        # OPTIONAL - required only if you specified PlayerFeature.PLAY_ANNOUNCEMENT
        # This method should handle the playback of an announcement on the given player.
        # The announcement object contains all the details needed to play the announcement.
        # The volume_level is optional and can be used to set the volume level for the announcement.
        # If you do not use the announcement playerfeature, the default behavior is to play the
        # announcement as a regular media item using the play_media method and the MA player manager
        # will take care of setting the volume level for the announcement and resuming etc.

    async def poll_player(self, player_id: str) -> None:
        """Poll player for state updates."""
        # OPTIONAL
        # This method is optional and should be implemented if you specified 'needs_poll'
        # on the Player object. This method should poll the player for state changes
        # and update the player object in the player manager if needed.
        # This method will be called at the interval specified in the poll_interval attribute.

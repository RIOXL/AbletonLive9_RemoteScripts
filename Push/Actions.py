#Embedded file name: /Users/versonator/Hudson/live/Projects/AppLive/Resources/MIDI Remote Scripts/Push/Actions.py
import Live
from _Framework.ControlSurfaceComponent import ControlSurfaceComponent
from _Framework.CompoundComponent import CompoundComponent
from _Framework.SubjectSlot import subject_slot
from _Framework.DisplayDataSource import DisplayDataSource
from _Framework.ModesComponent import SetAttributeMode, ModesComponent
from _Framework import Task
from _Framework.Util import forward_property
from _Framework.Dependency import depends
from MessageBoxComponent import Messenger
from ActionWithOptionsComponent import ActionWithSettingsComponent, OptionsComponent
from ClipControlComponent import convert_length_to_bars_beats_sixteenths
from BrowserModes import BrowserAddEffectMode
from consts import MessageBoxText

def convert_length_to_mins_secs(length_in_secs):
    if length_in_secs is None:
        return '-'
    mins = int(length_in_secs / 60.0)
    secs = int(length_in_secs % 60.0)
    return str(mins) + ':' + str('%02d' % secs)


def convert_beats_to_mins_secs(length_in_beats, tempo = 120.0):
    if length_in_beats is None:
        return '-'
    length_in_secs = length_in_beats / tempo * 60.0
    return convert_length_to_mins_secs(length_in_secs)


class CaptureAndInsertSceneComponent(ActionWithSettingsComponent, Messenger):

    def post_trigger_action(self):
        try:
            self.song().capture_and_insert_scene()
            self.show_notification(MessageBoxText.CAPTURE_AND_INSERT_SCENE % self.song().view.selected_scene.name.strip())
        except Live.Base.LimitationError:
            self.expect_dialog(MessageBoxText.SCENE_LIMIT_REACHED)


class DuplicateLoopComponent(ActionWithSettingsComponent, Messenger):

    def __init__(self, *a, **k):
        super(DuplicateLoopComponent, self).__init__(*a, **k)
        self._on_detail_clip_changed.subject = self.song().view

    @subject_slot('detail_clip')
    def _on_detail_clip_changed(self):
        self._update_action_button()

    @property
    def can_duplicate_loop(self):
        clip = self.song().view.detail_clip
        return clip and clip.is_midi_clip

    def _update_action_button(self):
        if self.can_duplicate_loop:
            super(DuplicateLoopComponent, self)._update_action_button()
        elif self._action_button and self.is_enabled():
            self._action_button.set_light('DefaultButton.Disabled')

    def trigger_action(self):
        if self.can_duplicate_loop:
            clip = self.song().view.detail_clip
            if clip != None:
                try:
                    clip.duplicate_loop()
                    self.show_notification(MessageBoxText.DUPLICATE_LOOP % dict(length=convert_length_to_bars_beats_sixteenths(clip.loop_end - clip.loop_start)))
                except RuntimeError:
                    pass


class DeleteSelectedClipComponent(ActionWithSettingsComponent, Messenger):
    """
    Component that deletes the selected clip when tapping
    """

    def post_trigger_action(self):
        slot = self.song().view.highlighted_clip_slot
        if slot != None and slot.has_clip:
            name = slot.clip.name
            slot.delete_clip()
            self.show_notification(MessageBoxText.DELETE_CLIP % name)


class DeleteSelectedSceneComponent(ActionWithSettingsComponent, Messenger):
    """
    Component for deleting the selected scene and launch the previous
    one in scene list mode
    """

    def post_trigger_action(self):
        try:
            song = self.song()
            name = song.view.selected_scene.name
            selected_scene_index = list(song.scenes).index(song.view.selected_scene)
            song.delete_scene(selected_scene_index)
            self.show_notification(MessageBoxText.DELETE_SCENE % name)
            new_scene = song.scenes[max(selected_scene_index - 1, 0)]
            song.view.selected_scene = new_scene
            new_scene.fire(force_legato=True)
        except RuntimeError:
            pass


class SelectionDisplayComponent(ControlSurfaceComponent):
    """
    This component handles display of selected objects.
    """
    num_segments = 4

    def __init__(self, *a, **k):
        super(SelectionDisplayComponent, self).__init__(*a, **k)
        self._data_sources = [ DisplayDataSource() for _ in range(self.num_segments) ]

    def set_display_line(self, display_line):
        if display_line != None:
            display_line.set_num_segments(self.num_segments)
            for idx in xrange(self.num_segments):
                display_line.segment(idx).set_data_source(self._data_sources[idx])

    def set_display_string(self, string, segment = 0):
        if segment < self.num_segments:
            self._data_sources[segment].set_display_string(string)

    def reset_display(self):
        for idx in xrange(self.num_segments):
            self._data_sources[idx].set_display_string(' ')

    def reset_display_right(self):
        for idx in xrange(self.num_segments / 2, self.num_segments):
            self._data_sources[idx].set_display_string(' ')

    def update(self):
        pass


class SelectComponent(CompoundComponent):
    """
    This component handles selection of objects.
    """

    def __init__(self, *a, **k):
        super(SelectComponent, self).__init__(*a, **k)
        self._selected_clip = None
        self._select_button = None
        self._selection_display = self.register_component(SelectionDisplayComponent())
        self._selection_display.set_enabled(False)

    selection_display_layer = forward_property('_selection_display')('layer')

    def set_select_button(self, button):
        if self._select_button != button:
            self._select_button = button
            self._on_select_value.subject = button

    def set_selected_clip(self, clip):
        self._selected_clip = clip
        self._on_playing_position_changed.subject = clip

    def on_select_clip(self, clip_slot):
        if clip_slot != None:
            if self.song().view.highlighted_clip_slot != clip_slot:
                self.song().view.highlighted_clip_slot = clip_slot
            if clip_slot.has_clip:
                clip = clip_slot.clip
                clip_name = clip.name if clip.name != '' else '[unnamed]'
                self.set_selected_clip(clip)
            else:
                clip_name = '[empty slot]'
                self.set_selected_clip(None)
        else:
            clip_name = '[none]'
        self._selection_display.set_display_string('Clip Selection:')
        self._selection_display.set_display_string(clip_name, 1)
        self._do_show_time_remaining()
        self._selection_display.set_enabled(True)

    @subject_slot('playing_position')
    def _on_playing_position_changed(self):
        self._do_show_time_remaining()

    def _do_show_time_remaining(self):
        clip = self._selected_clip
        if clip != None and (clip.is_triggered or clip.is_playing):
            if clip.is_recording:
                label = 'Record Count:'
                length = (clip.playing_position - clip.loop_start) * clip.signature_denominator / clip.signature_numerator
                time = convert_length_to_bars_beats_sixteenths(length)
            else:
                label = 'Time Remaining:'
                length = clip.loop_end - clip.playing_position
                if clip.is_audio_clip and not clip.warping:
                    time = convert_length_to_mins_secs(length)
                else:
                    time = convert_beats_to_mins_secs(length, self.song().tempo)
        else:
            label = ' '
            time = ' '
        self._selection_display.set_display_string(label, 2)
        self._selection_display.set_display_string(time, 3)

    def on_select_scene(self, scene):
        if scene != None:
            if self.song().view.selected_scene != scene:
                self.song().view.selected_scene = scene
            scene_name = scene.name if scene.name != '' else '[unnamed]'
        else:
            scene_name = '[none]'
        self._selection_display.set_display_string('Scene Selection:')
        self._selection_display.set_display_string(scene_name, 1)
        self._selection_display.reset_display_right()
        self._selection_display.set_enabled(True)

    def on_select_track(self, track):
        if track != None:
            track_name = track.name if track.name != '' else '[unnamed]'
        else:
            track_name = '[none]'
        self._selection_display.set_display_string('Track Selection:')
        self._selection_display.set_display_string(track_name, 1)
        self._selection_display.reset_display_right()
        self._selection_display.set_enabled(True)

    def on_select_drum_pad(self, drum_pad):
        if drum_pad != None:
            drum_pad_name = drum_pad.name if drum_pad.name != '' else '[unnamed]'
        else:
            drum_pad_name = '[none]'
        self._selection_display.set_display_string('Pad Selection:')
        self._selection_display.set_display_string(drum_pad_name, 1)
        self._selection_display.reset_display_right()
        self._selection_display.set_enabled(True)

    @subject_slot('value')
    def _on_select_value(self, value):
        if value == 0:
            self._selection_display.set_enabled(False)
            self._selection_display.reset_display()
            self.set_selected_clip(None)

    def update(self):
        pass


class DeleteComponent(ControlSurfaceComponent, Messenger):
    """
    Component for handling deletion of parameters
    """

    def __init__(self, *a, **k):
        super(DeleteComponent, self).__init__(*a, **k)
        self._delete_button = None

    def set_delete_button(self, button):
        self._delete_button = button

    @property
    def is_deleting(self):
        return self._delete_button and self._delete_button.is_pressed()

    def delete_clip_envelope(self, parameter):
        playing_clip = self._get_playing_clip()
        if playing_clip:
            playing_clip.clear_envelope(parameter)
            self.show_notification(MessageBoxText.DELETE_ENVELOPE % dict(automation=parameter.name))

    def _get_playing_clip(self):
        selected_track = self.song().view.selected_track
        playing_slot_index = selected_track.playing_slot_index
        if playing_slot_index >= 0:
            return selected_track.clip_slots[playing_slot_index].clip

    def update(self):
        pass


class CreateDefaultTrackComponent(CompoundComponent, Messenger):

    @depends(selection=None)
    def __init__(self, selection = None, *a, **k):
        super(CreateDefaultTrackComponent, self).__init__(*a, **k)
        self.options = self.register_component(OptionsComponent())
        self.options.selected_option = None
        self.options.default_option_names = ('Audio', 'Midi', 'Return')
        self.options.labels = ('Create track:', '', '', '')
        self.options.selected_color = 'Browser.Load'
        self.options.unselected_color = 'Browser.Load'
        self._on_option_selected.subject = self.options
        self._selection = selection

    @subject_slot('selected_option')
    def _on_option_selected(self, option):
        if option is not None:
            self.create_track()
            self.options.selected_option = None

    def create_track(self):
        try:
            song = self.song()
            selected_track = self._selection.selected_track
            idx = list(song.tracks).index(selected_track) + 1 if selected_track in song.tracks else -1
            selected_option = self.options.selected_option
            if selected_option == 0:
                song.create_audio_track(idx)
            elif selected_option == 1:
                song.create_midi_track(idx)
            elif selected_option == 2:
                song.create_return_track()
        except Live.Base.LimitationError:
            self.expect_dialog(MessageBoxText.TRACK_LIMIT_REACHED)
        except RuntimeError:
            self.expect_dialog(MessageBoxText.MAX_RETURN_TRACKS_REACHED)

    def on_enabled_changed(self):
        self.options.selected_option = None

    def update(self):
        pass


class CreateInstrumentTrackComponent(CompoundComponent, Messenger):

    @depends(selection=None)
    def __init__(self, selection = None, browser_mode = None, browser_component = None, browser_hotswap_mode = None, *a, **k):
        super(CreateInstrumentTrackComponent, self).__init__(*a, **k)
        self._selection = selection
        self._with_browser_modes = self.register_component(ModesComponent())
        self._with_browser_modes.add_mode('create', [self._prepare_browser,
         SetAttributeMode(self.application().browser, 'filter_type', Live.Browser.FilterType.instrument_hotswap),
         SetAttributeMode(browser_component, 'do_load_item', self._do_browser_load_item),
         browser_mode,
         browser_component.reset_load_memory])
        self._with_browser_modes.add_mode('hotswap', [browser_hotswap_mode, browser_mode])
        self._go_to_hotswap_task = self._tasks.add(Task.sequence(Task.delay(1), Task.run(self._go_to_hotswap)))
        self._go_to_hotswap_task.kill()

    def on_enabled_changed(self):
        self._with_browser_modes.selected_mode = 'create' if self.is_enabled() else None
        self._go_to_hotswap_task.kill()

    def _prepare_browser(self):
        if self.application().view.browse_mode:
            self.application().view.toggle_browse()

    def _do_browser_load_item(self, item):
        song = self.song()
        selected_track = self._selection.selected_track
        idx = list(song.tracks).index(selected_track) + 1 if selected_track in song.tracks else -1
        try:
            song.create_midi_track(idx)
        except Live.Base.LimitationError:
            self.expect_dialog(MessageBoxText.TRACK_LIMIT_REACHED)

        item.action()
        self._go_to_hotswap_task.restart()

    def _go_to_hotswap(self):
        self._with_browser_modes.selected_mode = 'hotswap'

    def update(self):
        pass


class CreateDeviceComponent(CompoundComponent):

    @depends(selection=None)
    def __init__(self, selection = None, browser_component = None, browser_mode = None, browser_hotswap_mode = None, insert_left = False, *a, **k):
        super(CreateDeviceComponent, self).__init__(*a, **k)
        self._selection = selection
        self._add_effect_mode = BrowserAddEffectMode(selection=selection, browser=self.application().browser, application_view=self.application().view, insert_left=insert_left)
        self._create_device_modes = self.register_component(ModesComponent())
        self._create_device_modes.add_mode('create', [SetAttributeMode(browser_component, 'do_load_item', self._do_browser_load_item),
         self._add_effect_mode,
         browser_mode,
         browser_component.reset_load_memory])
        self._create_device_modes.add_mode('hotswap', [browser_hotswap_mode, browser_mode])
        self._go_to_hotswap_task = self._tasks.add(Task.sequence(Task.delay(1), Task.run(self._go_to_hotswap)))
        self._go_to_hotswap_task.kill()

    def on_enabled_changed(self):
        self._go_to_hotswap_task.kill()
        if self.is_enabled():
            selected = self._selection.selected_object
            if isinstance(selected, Live.DrumPad.DrumPad) and (not selected.chains or not selected.chains[0].devices):
                self._create_device_modes.selected_mode = 'hotswap'
            else:
                self._create_device_modes.selected_mode = 'create'

    def update(self):
        pass

    def _go_to_hotswap(self):
        self._create_device_modes.selected_mode = 'hotswap'

    def _do_browser_load_item(self, item):
        selection = self._add_effect_mode.get_selection_for_insert()
        if selection:
            self._selection.selected_object = selection
        item.action()
        self._go_to_hotswap_task.restart()
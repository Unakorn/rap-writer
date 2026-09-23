"""Validate the portable musical song map shared with lyric generators."""
from __future__ import annotations

import json
import math
import re
import unicodedata


class SongStructureError(ValueError):
    pass


def _text(value, label, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise SongStructureError(f'{label} must be text up to {maximum} characters.')
    if any(unicodedata.category(char) in ('Cc', 'Cf', 'Cs') for char in value):
        raise SongStructureError(f'{label} contains an unsupported control character.')
    if not empty and not value.strip():
        raise SongStructureError(f'{label} cannot be empty.')
    return value.strip()


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise SongStructureError(f'{label} must be a whole number from {minimum} to {maximum}.')
    return value


def _number(value, label, minimum=0, maximum=10000000):
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        raise SongStructureError(f'{label} must be a finite number from {minimum:g} to {maximum:g}.')
    return value


def validate_song_structure(value):
    """Return an independent, validated map; never repair a different arrangement."""
    top = {'format', 'version', 'title', 'genre', 'time_signature', 'total_bars', 'duration_seconds', 'sections'}
    required = {'id', 'name', 'kind', 'start_bar', 'end_bar', 'bars', 'start_seconds',
                'end_seconds', 'bpm', 'pattern', 'vocal_mode', 'suggested_lines', 'notes', 'instruments'}
    if not isinstance(value, dict) or set(value) != top:
        raise SongStructureError('Choose the exported Song Structure.json file, containing the complete song map.')
    if value['format'] != '16bar.song_structure' or type(value['version']) is not int or value['version'] != 1:
        raise SongStructureError('This song JSON format or version is unsupported.')
    if value['time_signature'] != [4, 4] or any(type(n) is not int for n in value['time_signature']):
        raise SongStructureError('This song map must use 4/4 time.')
    result = {'format': value['format'], 'version': 1,
              'title': _text(value['title'], 'Song title', 200),
              'genre': _text(value['genre'], 'Genre', 80), 'time_signature': [4, 4],
              'total_bars': _integer(value['total_bars'], 'Song bars', 1, 512),
              'duration_seconds': _number(value['duration_seconds'], 'Song duration', 0.001),
              'sections': []}
    if not isinstance(value['sections'], list) or not 1 <= len(value['sections']) <= 64:
        raise SongStructureError('A song map must contain between 1 and 64 ordered sections.')
    previous_bar, previous_seconds, lyric_lines = 0, 0.0, 0
    seen = set()
    for index, section in enumerate(value['sections'], 1):
        label = f'Section {index}'
        if not isinstance(section, dict) or set(section) != required:
            raise SongStructureError(f'{label} does not contain the complete musical section data.')
        identifier = _text(section['id'], f'{label} ID', 80)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier) or identifier in seen:
            raise SongStructureError('Song section IDs must be unique letters, numbers, underscores or hyphens.')
        seen.add(identifier)
        name = _text(section['name'], f'{label} name', 80)
        if any(char in name for char in '[]') or not any(char.isalnum() for char in name):
            raise SongStructureError('Section names need readable text without brackets or line breaks.')
        if section['kind'] not in ('intro', 'verse', 'pre_chorus', 'chorus', 'bridge', 'outro'):
            raise SongStructureError(f'{label} has an unsupported section kind.')
        if section['pattern'] not in ('A', 'B', 'AC', 'BC'):
            raise SongStructureError(f'{label} has an unsupported source pattern.')
        bars = _integer(section['bars'], f'{label} musical bars', 1, 512)
        start = _integer(section['start_bar'], f'{label} starting bar', 1, 512)
        end = _integer(section['end_bar'], f'{label} ending bar', 1, 512)
        if start != previous_bar + 1 or end != start + bars - 1:
            raise SongStructureError('Song sections must cover consecutive musical bars without gaps or overlaps.')
        start_seconds = _number(section['start_seconds'], f'{label} start time')
        end_seconds = _number(section['end_seconds'], f'{label} end time')
        bpm = _number(section['bpm'], f'{label} tempo', 0.01, 100000000)
        expected_duration = bars * 240 / bpm
        tolerance = max(0.05, expected_duration * 0.000001)
        if end_seconds <= start_seconds or abs(start_seconds - previous_seconds) > 0.05 or abs(end_seconds - start_seconds - expected_duration) > tolerance:
            raise SongStructureError('Song section timing must match its musical bars and tempo, without gaps or overlaps.')
        if section['vocal_mode'] not in ('instrumental', 'lyrics'):
            raise SongStructureError(f'{label} must be instrumental or lyrics.')
        count = _integer(section['suggested_lines'], f'{label} lyric lines', 0, 64)
        if (section['vocal_mode'] == 'instrumental' and count != 0) or (section['vocal_mode'] == 'lyrics' and count == 0):
            raise SongStructureError('Instrumental sections need 0 lyric lines; vocal sections need at least 1.')
        instruments = section['instruments']
        if not isinstance(instruments, list) or len(instruments) > 256:
            raise SongStructureError(f'{label} has an invalid instrument list.')
        clean = {'id': identifier, 'name': name, 'kind': section['kind'], 'start_bar': start,
                 'end_bar': end, 'bars': bars, 'start_seconds': start_seconds, 'end_seconds': end_seconds,
                 'bpm': bpm, 'pattern': section['pattern'], 'vocal_mode': section['vocal_mode'],
                 'suggested_lines': count, 'notes': _text(section['notes'], f'{label} notes', 2000, empty=True),
                 'instruments': [_text(item, f'{label} instrument', 160) for item in instruments]}
        result['sections'].append(clean)
        previous_bar, previous_seconds = end, end_seconds
        lyric_lines += count
    if previous_bar != result['total_bars'] or abs(previous_seconds - result['duration_seconds']) > 0.05:
        raise SongStructureError('The total song length does not match its sections.')
    if lyric_lines > 160:
        raise SongStructureError('Keep the full song at 160 lyric lines or fewer; musical bars are separate.')
    return result


def parse_song_structure(text):
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise SongStructureError('Choose a song JSON file smaller than 1 MB.')
    try:
        def unique_object(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise SongStructureError('The song JSON contains a repeated field name.')
                result[key] = item
            return result
        data = json.loads(text, object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as exc:
        raise SongStructureError('The song JSON could not be read. Choose the exported Song Structure.json file.') from exc
    return validate_song_structure(data)

from copy import deepcopy


def rap_idea():
    return dict(topic='You finally take your mother for dinner after paying back a small loan',
                details='A cracked phone screen, the last night bus, and two paper menus on the table.',
                hook_note='Keep a place for me', good_words='night bus, paper menus',
                style='Melodic rap', mood='Reflective / hopeful', phrasing='Melodic / pocketed',
                rhyme_style='Internal + end rhymes', dynamics='Rapped verses / sung hook',
                imagery='Concrete / personal')


def song_map():
    result = dict(format='16bar.song_structure', version=1, title='After the late shift',
                  genre='Melodic rap', time_signature=[4, 4], total_bars=34,
                  duration_seconds=68.0, sections=[])
    bar = 1
    for index, (name, kind, bars, lines) in enumerate([
        ('Intro', 'intro', 2, 0), ('Hook', 'chorus', 8, 4),
        ('Verse 1', 'verse', 16, 8), ('Hook', 'chorus', 8, 4),
    ], 1):
        result['sections'].append(dict(
            id=f'section_{index}', name=name, kind=kind, start_bar=bar,
            end_bar=bar + bars - 1, bars=bars, start_seconds=(bar - 1) * 2.0,
            end_seconds=(bar + bars - 1) * 2.0, bpm=120.0, pattern='A',
            vocal_mode='lyrics' if lines else 'instrumental', suggested_lines=lines,
            notes='Leave space for the answer', instruments=['Bass', 'Piano']))
        bar += bars
    return deepcopy(result)

from goga.data.daily import Pretendents


def test_Pretendents_add_participant():
    # arrange
    participants = Pretendents()

    # act
    participants.add_participant('participant1')
    participants.add_participant('participant2')
    participants.add_participant('participant3')

    # assert
    assert len(participants) == 3
    assert 'participant1' in participants
    assert 'participant2' in participants
    assert 'participant3' in participants


def test_Pretendents_pop():
    # arrange
    pretendents = Pretendents(['p1', 'p2', 'p3'])

    # act, assert
    assert len(pretendents) == 3
    assert pretendents.moderator == 'p3'
    pretendents.pop()

    assert len(pretendents) == 2
    assert pretendents.moderator == 'p2'
    pretendents.pop()

    assert len(pretendents) == 1
    assert pretendents.moderator == 'p1'
    pretendents.pop()

    assert len(pretendents) == 0
    assert pretendents.moderator is None

    pretendents.pop()
    assert len(pretendents) == 0


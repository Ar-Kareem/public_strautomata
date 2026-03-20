import random
import traceback
from typing import Any

from game_arena import utils
import inspect


def _move_to_str(move):
    if hasattr(move, "get_unparsed_str"):
        try:
            return move.get_unparsed_str()
        except Exception:
            pass
    return str(move)


_POLICIES = {}
_PENDING_HUMAN_ACTION = None


def _ensure_selected_policies(game_name, world_name, selected_bot_ids):
    key = (game_name, world_name)
    policies = _POLICIES.get(key)
    if policies is None:
        policies = {}
        _POLICIES[key] = policies
    for bot_id in selected_bot_ids:
        if not bot_id or bot_id in {"human", "random", "first", "last"}:
            continue
        if bot_id in policies:
            continue
        path = f"/home/src/game_arena/{game_name}/examples/{world_name}/{bot_id}/2.python_code.py"
        try:
            with open(path, "r") as f:
                code = f.read()
        except Exception as e:
            return f"Failed to read bot code for {bot_id}: {e}"
        policy_fn, msg = utils.get_policy_fn(code, path, f"{game_name}/{world_name}/{bot_id}")
        if policy_fn is None:
            return msg or f"Failed to compile bot code for {bot_id}"
        policies[bot_id] = utils.wrap_policy_fn_with_memory(policy_fn)
    return None


def _choose_action(game_name, world_name, policy_name, observation, legal_moves):
    if not legal_moves:
        return None
    if policy_name == "human":
        return None
    if policy_name == "first":
        return _move_to_str(legal_moves[0])
    if policy_name == "last":
        return _move_to_str(legal_moves[-1])
    if policy_name == "random":
        return _move_to_str(random.choice(legal_moves))
    policy = _POLICIES[(game_name, world_name)].get(policy_name)
    if policy is None:
        return _move_to_str(random.choice(legal_moves))
    kwargs = dict(observation)
    try:
        if "_debug_legal_moves" in inspect.signature(policy).parameters:
            kwargs["_debug_legal_moves"] = legal_moves
    except Exception:
        pass
    result = policy(**kwargs)  # type: ignore
    return result


def _safe_final_stats(game):
    try:
        return game.get_final_stats()
    except Exception as e:
        return {"error": str(e)}


def _winner_for_illegal(player):
    try:
        player_id = int(player)
    except Exception:
        return None
    if player_id in (0, 1):
        return 1 - player_id
    return None


_GAME = None
_TURN = 0
WORLD_NAME = ""


def init_match():
    global _GAME, _TURN, _PENDING_HUMAN_ACTION
    logs = []
    error = _ensure_selected_policies(GAME_NAME, WORLD_NAME, [BOT_A, BOT_B])
    if error:
        logs.append(error)
        return {"error": error, "logs": logs, "done": True}
    try:
        game_cls = utils.get_game(GAME_NAME)
        _GAME = game_cls(GAME_CONFIG)
    except Exception as e:
        tb = traceback.format_exc()
        logs.append("init_error_traceback:")
        logs.extend(tb.splitlines())
        return {"error": "Failed to initialize game: " + str(e) + "\\n" + tb, "logs": logs, "done": True}
    _TURN = 0
    _PENDING_HUMAN_ACTION = None
    logs.append(f"game={GAME_NAME} world=browser config={GAME_CONFIG}")
    return {"logs": logs, "done": False, "state_player": {
        "state": _GAME.get_fixed_observation(),  # type: ignore
        "player": _GAME.current_player(),
    }}


def policy_error(logs, policy_name, player):
    final_stats = _safe_final_stats(_GAME)
    winner = _winner_for_illegal(player)
    if winner is not None:
        if isinstance(final_stats, dict):
            final_stats: dict[str, Any] = dict(final_stats)
        else:
            final_stats = {}
        final_stats["winner"] = winner
        logs.append(f"illegal_move_winner={winner}")
    logs.append("final_stats=" + str(final_stats))
    return {
        "done": True,
        "final": final_stats,
        "illegal": True,
        "illegal_bot": policy_name,
        "illegal_action": None,
    }
    
def move_error(logs, e, policy_name, action, player):
    logs.append("Move error: " + str(e))
    logs.append(f"Illegal move by {policy_name}.")
    illegal_action = _move_to_str(action)
    logs.append(f"illegal_action={illegal_action}")
    final_stats = _safe_final_stats(_GAME)
    winner = _winner_for_illegal(player)
    if winner is not None:
        if isinstance(final_stats, dict):
            final_stats: dict[str, Any] = dict(final_stats)
        else:
            final_stats = {}
        final_stats["winner"] = winner
        logs.append(f"illegal_move_winner={winner}")
    logs.append("final_stats=" + str(final_stats))
    return {
        "done": True,
        "final": final_stats,
        "illegal": True,
        "illegal_bot": policy_name,
        "illegal_action": illegal_action,
    }

def step_match():
    global _GAME, _TURN
    global _PENDING_HUMAN_ACTION
    logs = []
    return_kwargs = {
        "logs": logs,
        "state_player": None
    }
    if _GAME is None:
        return {"error": "No game initialized", "done": True, **return_kwargs}
    if (GAME_NAME, WORLD_NAME) not in _POLICIES:
        return {"error": "no policies found for game/world", "done": True, **return_kwargs}
    if _GAME.is_done():
        final_stats = _safe_final_stats(_GAME)
        logs.append("final_stats=" + str(final_stats))
        return {"done": True, "final": final_stats, **return_kwargs}
    if hasattr(_GAME, "get_fixed_observation"):
        observation = _GAME.get_fixed_observation()  # type: ignore
        bot_observation = _GAME.get_observation()
    else:
        observation = _GAME.get_observation()
        bot_observation = observation
    player = _GAME.current_player()
    return_kwargs["state_player"] = {
        "state": observation,
        "player": player,
    }
    legal_moves = _GAME.get_legal_moves()
    legal_move_strings = [_move_to_str(move) for move in legal_moves]
    sample = ", ".join(legal_move_strings[:8])
    logs.append(
        f"turn={_TURN} player={player} legal_moves={len(legal_moves)} sample=[{sample}]"
    )
    if observation is not None and "board" in observation:
        logs.append("board=" + str(observation["board"]))
    else:
        logs.append("observation=" + str(observation))
    try:
        logs.append("state_pre_move=\n" + str(_GAME._state))  # type: ignore
    except Exception as e:
        logs.append("Exception: error getting state before move: " + str(e))
    policy_name = BOT_A if player == 0 else BOT_B
    action = None
    if policy_name == "human":
        if _PENDING_HUMAN_ACTION is None:
            return {
                "done": False,
                "awaiting_input": True,
                "legal_moves": legal_move_strings,
                **return_kwargs,
            }
        pending_human_action = _PENDING_HUMAN_ACTION
        _PENDING_HUMAN_ACTION = None
        force_apply = False
        if isinstance(pending_human_action, dict):
            action = pending_human_action.get("action")
            force_apply = bool(pending_human_action.get("force_apply", False))
        else:
            action = pending_human_action
        action_str = str(action)
        if force_apply:
            logs.append(f"Force-applying human move: {action_str}")
        if not force_apply and action_str not in legal_move_strings:
            logs.append(f"Invalid human move: {action_str}")
            return {
                "done": False,
                "awaiting_input": True,
                "legal_moves": legal_move_strings,
                "invalid_move": action_str,
                **return_kwargs,
            }
    else:
        try:
            action = _choose_action(game_name=GAME_NAME, world_name=WORLD_NAME, policy_name=policy_name, observation=bot_observation, legal_moves=legal_moves)
        except Exception as e:
            logs.append(f"Exception: error executing policy for {policy_name}: " + str(e) + "\n" + traceback.format_exc())
            return {**policy_error(logs, policy_name, player), **return_kwargs}
    if action is None:
        logs.append(f"Action was none by {policy_name}. Not allowed.")
        return {**policy_error(logs, policy_name, player), **return_kwargs}
    action_for_move = action
    if isinstance(action_for_move, str) and action_for_move in legal_move_strings:  # human move will be here
        try:
            idx = legal_move_strings.index(action_for_move)
            candidate = legal_moves[idx]
            if isinstance(candidate, tuple):
                action_for_move = candidate
        except Exception as e:
            logs.append("Exception: error getting index: " + str(e))
    if hasattr(action, "get_unparsed_str"):
        try:
            action_for_move = action.get_unparsed_str()  # type: ignore
        except Exception as e:
            logs.append("Exception: error getting unparsed str: " + str(e))
            action_for_move = action
    logs.append(f"{policy_name} chooses {_move_to_str(action)}")
    try:
        action_obj = _GAME.get_move(action_for_move)  # type: ignore
        _GAME.game_step(action_obj)  # type: ignore
    except Exception as e:
        logs.append("Exception: error getting move: " + str(e) + "\n" + traceback.format_exc())
        return {**move_error(logs, e, policy_name, action, player), **return_kwargs}
    try:
        if hasattr(_GAME, "get_fixed_observation"):
            new_observation = _GAME.get_fixed_observation()  # type: ignore
        else:
            new_observation = _GAME.get_observation()
        logs.append('new_observation=' + str(new_observation))
        return_kwargs["state_player"] = {
            "state": new_observation,
            "player": _GAME.current_player(),
            "old_state": return_kwargs["state_player"]["state"],
            "old_player": return_kwargs["state_player"]["player"],
            "action": action_for_move,
        }
    except Exception as e:
        logs.append("Exception: error getting new observation: " + str(e))
    try:
        logs.append("state_post_move=\n" + str(_GAME._state))  # type: ignore
    except Exception:
        logs.append("Exception: error getting state after move")
    _TURN += 1
    if _GAME.is_done():
        final_stats = _safe_final_stats(_GAME)
        logs.append("final_stats=" + str(final_stats))
        return {"done": True, "final": final_stats, **return_kwargs}
    return {"done": False, **return_kwargs}


def submit_human_move(action, force_apply=False):
    global _PENDING_HUMAN_ACTION
    _PENDING_HUMAN_ACTION = {"action": action, "force_apply": bool(force_apply)}
    return step_match()

if __name__ == "__main__":
    GAME_NAME: Any
    GAME_CONFIG: Any
    BOT_A: Any
    BOT_B: Any

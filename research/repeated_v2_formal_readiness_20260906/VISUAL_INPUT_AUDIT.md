# Actual VLA input visual check

Viewed the retained rendered RGB from the passed real-action probe (task1, state0). The image contains a nonblank, textured tabletop scene with the robot gripper, basket and packaged objects. No diagnostic overlay or canonical-state annotation is visible. The native image-preprocessing path is separately source-pinned in the probe.

Source: `action_probe_01/REAL_RENDERED_INPUT.txt`; raw RGB SHA256 `3a3622459987744fab350ca0c1740c69f5f5416b77c7a37c318f6287b881a4d4`; shape `[224, 224, 3]`, uint8 range 0–255, standard deviation 44.032581887.

This is a rendering/input check, not a task-success, detector-accuracy or event-safety certificate. A temporary PNG was decoded only for inspection; the original RGB bytes and their hash remain the retained evidence.

Also inspected the completed task0/state0/seed101 terminal RGB without changing or replaying the episode. The rendered tabletop, robot and objects remain visible; the image is not blank or an error screen. Its terminal goal outcome is determined by the recorded exact LIBERO predicates, not this visual inspection. Observation artifact SHA256: `b1d27a3b1d06fa77aa7a62eb316466d0414eba804b9730a8ed727d5de778b786`; raw RGB SHA256: `4743af9e46445225b043f690ee593c4496f1acb30083b7776f15b952bf3c9e9c`. Source: `clean_calibration_01/task_0_state_0_seed_101/TERMINAL_OBSERVATION.txt` on the calibration host, to be retained unchanged with the completed cohort.

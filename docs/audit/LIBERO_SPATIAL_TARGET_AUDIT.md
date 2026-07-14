# LIBERO Spatial Target Joint Audit

- Suite: `libero_spatial`
- Generated: `2026-07-14 17:28:09 +0800`
- Disturbance probe: `dx=0.10, dy=0.05, dz=0.00` on initial state 0
- Constraints honored: no OpenVLA load, no policy rollout, no Dashboard use, no dependency upgrade, no success-criterion change.
- Reachability is not claimed; the audit records only geometric and camera/workspace proxies.

## Summary

| task | description | recommended target_joint | auto reliable | manual review | geometric | camera visible | noop step |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | pick up the black bowl between the plate and the ramekin and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | no | yes | no |
| 1 | pick up the black bowl next to the ramekin and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 2 | pick up the black bowl from table center and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | no | yes | no |
| 3 | pick up the black bowl on the cookie box and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 4 | pick up the black bowl in the top drawer of the wooden cabinet and place it on the plate | `akita_black_bowl_2_joint0` | no | yes | yes | yes | no |
| 5 | pick up the black bowl on the ramekin and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 6 | pick up the black bowl next to the cookie box and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 7 | pick up the black bowl on the stove and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 8 | pick up the black bowl next to the plate and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |
| 9 | pick up the black bowl on the wooden cabinet and place it on the plate | `akita_black_bowl_1_joint0` | no | yes | yes | yes | no |

## Pilot Recommendation

- Task 1: `akita_black_bowl_1_joint0`. Selected for small-batch pilot because the target joint is explicit, the dx/dy disturbance passed geometric sanity, the policy-camera proxy changed, and it adds spatial cues ['next to', 'on', 'in'].
- Task 4: `akita_black_bowl_2_joint0`. Selected for small-batch pilot because the target joint is explicit, the dx/dy disturbance passed geometric sanity, the policy-camera proxy changed, and it adds spatial cues ['on', 'in'].
- Task 3: `akita_black_bowl_1_joint0`. Selected for small-batch pilot because the target joint is explicit, the dx/dy disturbance passed geometric sanity, the policy-camera proxy changed, and it adds spatial cues ['on'].

## Task Details

### Task 0

- Description: pick up the black bowl between the plate and the ramekin and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: closest to midpoint between plate_1 and glazed_rim_porcelain_ramekin_1 (midpoint_distance=0.0098, balance=0.0176)
- Alternate candidates: `akita_black_bowl_2_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`, `plate_1_joint0`, `cookies_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [-0.06348281771240429, 0.20206256199913958, 0.97] | 2 | 2 | closest to midpoint between plate_1 and glazed_rim_porcelain_ramekin_1 (midpoint_distance=0.0098, balance=0.0176) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [-0.1887304942403383, 0.32038450296164156, 0.97] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.1973841700047281, 0.1891352613576224, 0.97] | 1 | 0 |  | ramekin |  | no | 1 overlapping task/object tokens |
| `plate_1_joint0` | [0.053409166801723335, 0.2051823366186246, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.057859587539025564, 0.0264329413431314, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[-0.06348281771240429, 0.20206256199913958, 0.97], after=[0.03651718228759572, 0.25206256199913957, 0.97], actual_delta=[0.1, 0.04999999999999999, 0.0], changed_pixels=1675, geometric_sanity=no, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=yes, restore_successful=yes.

### Task 1

- Description: pick up the black bowl next to the ramekin and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule nearest uses reference glazed_rim_porcelain_ramekin_1 (xy_distance=0.1218, candidate_z=0.9700, reference_z=0.9700)
- Alternate candidates: `akita_black_bowl_2_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`, `plate_1_joint0`, `cookies_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [-0.19485644198162994, 0.31525765332242334, 0.97] | 2 | 2 | spatial rule nearest uses reference glazed_rim_porcelain_ramekin_1 (xy_distance=0.1218, candidate_z=0.9700, reference_z=0.9700) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [0.1381842936365544, -0.08494594969759002, 0.97] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.1857810556196215, 0.19377194917599047, 0.97] | 1 | 0 |  | ramekin |  | no | 1 overlapping task/object tokens |
| `plate_1_joint0` | [0.06977007762496036, 0.1881749872765843, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.06434455534203182, 0.031479971897618364, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[-0.19485644198162994, 0.31525765332242334, 0.97], after=[-0.09485644198162993, 0.3652576533224233, 0.97], actual_delta=[0.1, 0.04999999999999999, 0.0], changed_pixels=857, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 2

- Description: pick up the black bowl from table center and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: closest to table-center proxy at xy=(0, 0) (distance=0.0765)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [-0.07500000000000001, 0.014998007260810334, 0.97] | 2 | 2 | closest to table-center proxy at xy=(0, 0) (distance=0.0765) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [-0.002351721896208643, 0.3068892375372861, 0.97] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.07159545509386209, 0.2003926940191166, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.07668303942933519, 0.03753319957690388, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.20139241383137313, 0.18698477058544463, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[-0.07500000000000001, 0.014998007260810334, 0.97], after=[0.024999999999999994, 0.06499800726081034, 0.97], actual_delta=[0.1, 0.05000000000000001, 0.0], changed_pixels=1630, geometric_sanity=no, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=yes, restore_successful=yes.

### Task 3

- Description: pick up the black bowl on the cookie box and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule on_top_or_near uses reference cookies_1 (xy_distance=0.0000, candidate_z=1.0800, reference_z=0.9700)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [0.06784034305025467, 0.023905893540960326, 1.08] | 2 | 2 | spatial rule on_top_or_near uses reference cookies_1 (xy_distance=0.0000, candidate_z=1.0800, reference_z=0.9700) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [0.02247647122004687, -0.284100844023198, 1.2315200000000002] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.06976083146295943, 0.19004703438271336, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.06784034305025467, 0.023905893540960326, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.21386147234997907, 0.2108978598041229, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[0.06784034305025467, 0.023905893540960326, 1.08], after=[0.1678403430502547, 0.07390589354096033, 1.08], actual_delta=[0.10000000000000002, 0.05, 0.0], changed_pixels=1747, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 4

- Description: pick up the black bowl in the top drawer of the wooden cabinet and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_2_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_2_joint0: spatial rule inside_or_on_furniture uses reference wooden_cabinet_1_main (xy_distance=0.0262, candidate_z=1.2315, reference_z=0.9050)
- Alternate candidates: `akita_black_bowl_1_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [0.0851332502478196, -0.12994511970492176, 1.15063] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [0.017517315725231596, -0.2774597937798483, 1.2315200000000002] | 2 | 2 | spatial rule inside_or_on_furniture uses reference wooden_cabinet_1_main (xy_distance=0.0262, candidate_z=1.2315, reference_z=0.9050) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.05506639663695308, 0.20966968744965908, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.07277030707755008, 0.0407976769849453, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.20235947518173747, 0.19182370012223274, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[0.017517315725231596, -0.2774597937798483, 1.2315200000000002], after=[0.11751731572523161, -0.22745979377984832, 1.2315200000000002], actual_delta=[0.1, 0.04999999999999999, 0.0], changed_pixels=1086, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 5

- Description: pick up the black bowl on the ramekin and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule on_top_or_near uses reference glazed_rim_porcelain_ramekin_1 (xy_distance=0.0000, candidate_z=1.0800, reference_z=0.9700)
- Alternate candidates: `akita_black_bowl_2_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`, `plate_1_joint0`, `cookies_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [-0.19682435662356162, 0.20173353583306847, 1.08] | 2 | 2 | spatial rule on_top_or_near uses reference glazed_rim_porcelain_ramekin_1 (xy_distance=0.0000, candidate_z=1.0800, reference_z=0.9700) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [0.05681204483545177, 0.042538288814406265, 1.08] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.19682435662356162, 0.20173353583306847, 0.97] | 1 | 0 |  | ramekin |  | no | 1 overlapping task/object tokens |
| `plate_1_joint0` | [0.07346006601438027, 0.18547703940102553, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.05681204483545177, 0.042538288814406265, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[-0.19682435662356162, 0.20173353583306847, 1.08], after=[-0.09682435662356162, 0.25173353583306846, 1.08], actual_delta=[0.1, 0.04999999999999999, 0.0], changed_pixels=1163, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 6

- Description: pick up the black bowl next to the cookie box and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule nearest uses reference cookies_1 (xy_distance=0.1217, candidate_z=0.9700, reference_z=0.9700)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [0.13733616561092005, -0.07043152905820577, 0.97] | 2 | 2 | spatial rule nearest uses reference cookies_1 (xy_distance=0.1217, candidate_z=0.9700, reference_z=0.9700) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [-0.26254132223015614, -0.13541186011159, 1.01] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.06889841023405889, 0.19442333859141608, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.07341313846842597, 0.03312639987921978, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.21327251119735047, 0.18949124419433638, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[0.13733616561092005, -0.07043152905820577, 0.97], after=[0.23733616561092005, -0.020431529058205763, 0.97], actual_delta=[0.1, 0.05, 0.0], changed_pixels=1731, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 7

- Description: pick up the black bowl on the stove and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule on_top_or_near uses reference flat_stove_1_main (xy_distance=0.1383, candidate_z=1.0100, reference_z=0.9050)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [-0.2621465774637912, -0.13139198629843865, 1.01] | 2 | 2 | spatial rule on_top_or_near uses reference flat_stove_1_main (xy_distance=0.1383, candidate_z=1.0100, reference_z=0.9050) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [0.03896240134330575, -0.2823638562218253, 1.2315200000000002] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.06007411385131641, 0.20497603375866488, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.056841395147385065, 0.02341409336003745, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.193181463804805, 0.2088010629884112, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[-0.2621465774637912, -0.13139198629843865, 1.01], after=[-0.1621465774637912, -0.08139198629843865, 1.01], actual_delta=[0.1, 0.05, 0.0], changed_pixels=1408, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 8

- Description: pick up the black bowl next to the plate and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule nearest uses reference plate_1 (xy_distance=0.1194, candidate_z=0.9700, reference_z=0.9700)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [0.007128605032953369, 0.2982832159972166, 0.97] | 2 | 2 | spatial rule nearest uses reference plate_1 (xy_distance=0.1194, candidate_z=0.9700, reference_z=0.9700) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [-0.1786715657145501, 0.31024522983226266, 0.97] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.055177961640832364, 0.18896262340960737, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.07006202671395616, 0.044645695828825896, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.19487269994481637, 0.20972718049962472, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[0.007128605032953369, 0.2982832159972166, 0.97], after=[0.10712860503295338, 0.34828321599721657, 0.97], actual_delta=[0.1, 0.04999999999999999, 0.0], changed_pixels=970, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

### Task 9

- Description: pick up the black bowl on the wooden cabinet and place it on the plate
- Initial states: 50
- Direct-object phrase: `black bowl`
- Auto reliable: no
- Ambiguous: yes
- Manual review required: yes
- Recommended explicit target_joint: `akita_black_bowl_1_joint0`
- Selection reason: Auto token matching tied among same-named manipulated objects; manual spatial semantics select akita_black_bowl_1_joint0: spatial rule inside_or_on_furniture uses reference wooden_cabinet_1_main (xy_distance=0.0024, candidate_z=1.2315, reference_z=0.9050)
- Alternate candidates: `akita_black_bowl_2_joint0`, `plate_1_joint0`, `cookies_1_joint0`, `glazed_rim_porcelain_ramekin_1_joint0`

| candidate | pos xyz | score | semantic | spatial | text tokens | direct tokens | tied | reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `akita_black_bowl_1_joint0` | [0.038944822138478094, -0.2651063558710821, 1.2315200000000002] | 2 | 2 | spatial rule inside_or_on_furniture uses reference wooden_cabinet_1_main (xy_distance=0.0024, candidate_z=1.2315, reference_z=0.9050) | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `akita_black_bowl_2_joint0` | [-0.25166824114439823, -0.1413688691282905, 1.01] | 2 | 2 |  | black, bowl | black, bowl | yes | 2 overlapping task/object tokens |
| `plate_1_joint0` | [0.048217706605836394, 0.21470529653592868, 0.97] | 1 | 0 |  | plate |  | no | 1 overlapping task/object tokens |
| `cookies_1_joint0` | [0.0666981133542037, 0.028227396877703467, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |
| `glazed_rim_porcelain_ramekin_1_joint0` | [-0.20200226251826095, 0.20481742663834107, 0.97] | 0 | 0 |  |  |  | no | 0 overlapping task/object tokens |

- Disturbance: before=[0.038944822138478094, -0.2651063558710821, 1.2315200000000002], after=[0.13894482213847809, -0.21510635587108212, 1.2315200000000002], actual_delta=[0.09999999999999999, 0.04999999999999999, 0.0], changed_pixels=1216, geometric_sanity=yes, camera_visibility_proxy=yes, workspace_bound_proxy=yes, consumed_noop_env_step=no, simulator_stable=yes, has_nan_or_inf=no, obvious_table_or_object_penetration_proxy=no, restore_successful=yes.

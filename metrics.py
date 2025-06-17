import numpy as np

JOINT_NAMES = [
    "nose",
    "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear",
    "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

JOINT_IDX = { name: i for i, name in enumerate(JOINT_NAMES) }

ANGLE_TRIPLES = {
    'left_ankle': ('left_knee', 'left_ankle', 'left_foot_index'),
    'right_ankle': ('right_knee', 'right_ankle', 'right_foot_index'),
    'left_knee':  ('left_hip','left_knee','left_ankle'),
    'right_knee': ('right_hip','right_knee','right_ankle'),
    'left_elbow': ('left_shoulder','left_elbow','left_wrist'),
    'right_elbow':('right_shoulder','right_elbow','right_wrist'),
}

def joint_errors(user_pts, ideal_pts, included=None):
    # user_pts, ideal_pts: (N,2) arrays of normalized x,y
    if included is None:
        joints = JOINT_IDX.keys()
    else:
        joints = included

    # Torso normalization: distance between left and right hip
    torso_dist = np.linalg.norm(user_pts[JOINT_IDX['left_hip']] - user_pts[JOINT_IDX['right_hip']]) + 1e-6

    errors = {}
    for name in joints:
        idx = JOINT_IDX.get(name)
        if idx is None:
            continue
        d = np.linalg.norm(user_pts[idx] - ideal_pts[idx])
        errors[name] = float(d / torso_dist)
    return errors

def angle(a, b, c):
    v1 = a - b
    v2 = c - b
    cos = np.dot(v1, v2) / (np.linalg.norm(v1)*np.linalg.norm(v2) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))

def angle_errors(user_pts, ideal_pts, included=None):
    if included is None:
        triples = ANGLE_TRIPLES
    else:
        triples = {k: ANGLE_TRIPLES[k] for k in included if k in ANGLE_TRIPLES}

    errs = {}
    for name, (p, v, c) in triples.items():
        idx_p, idx_v, idx_c = JOINT_IDX[p], JOINT_IDX[v], JOINT_IDX[c]
        user_angle = angle(user_pts[idx_p], user_pts[idx_v], user_pts[idx_c])
        ideal_angle = angle(ideal_pts[idx_p], ideal_pts[idx_v], ideal_pts[idx_c])
        errs[name] = abs(user_angle - ideal_angle)
    return errs

def aggregate_score(joint_errs, angle_errs, w_joint=0.6, w_angle=0.4):
    mean_j = np.mean(list(joint_errs.values()))
    mean_a = np.mean(list(angle_errs.values())) / 180.0
    score = 1 - (w_joint * mean_j + w_angle * mean_a)
    return float(np.clip(score, 0, 1))

def build_feature_vector(timestamp, joint_errs, angle_errs):
    return {
      'timestamp': timestamp,
      'joint_errors': joint_errs,
      'angle_errors': angle_errs,
      'overall_score': aggregate_score(joint_errs, angle_errs)
    }
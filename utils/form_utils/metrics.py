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
    """Calculate joint position errors between user and ideal poses."""
    errors = {}
    
    # Define joint indices
    joints = {
        'nose': 0,
        'left_shoulder': 11,
        'right_shoulder': 12,
        'left_elbow': 13,
        'right_elbow': 14,
        'left_wrist': 15,
        'right_wrist': 16,
        'left_hip': 23,
        'right_hip': 24,
        'left_knee': 25,
        'right_knee': 26,
        'left_ankle': 27,
        'right_ankle': 28
    }
    
    # Filter joints if included list is provided
    if included:
        joints = {k: v for k, v in joints.items() if k in included}
    
    for joint_name, idx in joints.items():
        if idx < len(user_pts) and idx < len(ideal_pts):
            # Calculate Euclidean distance between points
            error = np.sqrt(np.sum((user_pts[idx] - ideal_pts[idx]) ** 2))
            errors[joint_name] = error
    
    return errors

def angle(a, b, c):
    v1 = a - b
    v2 = c - b
    cos = np.dot(v1, v2) / (np.linalg.norm(v1)*np.linalg.norm(v2) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))

def angle_errors(user_pts, ideal_pts, included=None):
    """Calculate angle errors between user and ideal poses."""
    errors = {}
    
    # Define angles to calculate
    angles = {
        'left_elbow': (11, 13, 15),  # shoulder, elbow, wrist
        'right_elbow': (12, 14, 16),
        'left_shoulder': (13, 11, 23),  # elbow, shoulder, hip
        'right_shoulder': (14, 12, 24),
        'left_hip': (11, 23, 25),  # shoulder, hip, knee
        'right_hip': (12, 24, 26),
        'left_knee': (23, 25, 27),  # hip, knee, ankle
        'right_knee': (24, 26, 28)
    }
    
    # Filter angles if included list is provided
    if included:
        angles = {k: v for k, v in angles.items() if k in included}
    
    for angle_name, (p1_idx, p2_idx, p3_idx) in angles.items():
        if all(idx < len(user_pts) for idx in [p1_idx, p2_idx, p3_idx]) and \
           all(idx < len(ideal_pts) for idx in [p1_idx, p2_idx, p3_idx]):
            
            # Calculate angles
            user_angle = angle(user_pts[p1_idx], user_pts[p2_idx], user_pts[p3_idx])
            ideal_angle = angle(ideal_pts[p1_idx], ideal_pts[p2_idx], ideal_pts[p3_idx])
            
            # Calculate absolute difference
            error = abs(user_angle - ideal_angle)
            errors[angle_name] = error
    
    return errors

def calculate_angle(p1, p2, p3):
    """Calculate angle between three points."""
    v1 = p1 - p2
    v2 = p3 - p2
    
    # Calculate angle using dot product
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    cos_angle = np.clip(cos_angle, -1.0, 1.0)  # Ensure value is in valid range
    angle = np.arccos(cos_angle)
    
    return np.degrees(angle)

def aggregate_score(joint_errs, angle_errs, w_joint=0.6, w_angle=0.4):
    mean_j = np.mean(list(joint_errs.values()))
    mean_a = np.mean(list(angle_errs.values())) / 180.0
    score = 1 - (w_joint * mean_j + w_angle * mean_a)
    return float(np.clip(score, 0, 1))

def build_feature_vector(t_sec, joint_errs, angle_errs):
    return {
      'timestamp': t_sec,
      'joint_errors': joint_errs,
      'angle_errors': angle_errs,
      'overall_score': aggregate_score(joint_errs, angle_errs)
    }
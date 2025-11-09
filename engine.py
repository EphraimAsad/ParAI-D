import pandas as pd
import re

class ParasiteIdentifier:
    def __init__(self, data: pd.DataFrame):
        # Clean and standardize dataset
        self.df = data.copy()
        self.df.columns = [c.strip() for c in self.df.columns]

    # --- UTILITIES ---

    def _split_values(self, val):
        """Splits semicolon-separated entries and trims spaces."""
        if pd.isna(val):
            return []
        return [v.strip().lower() for v in str(val).split(";")]

    def _match_any(self, user_inputs, stored_values):
        """Returns True if any user entry matches dataset entries."""
        return any(u in stored_values for u in user_inputs)

    # --- SCORING ENGINE ---

    def score_entry(self, user_input: dict):
        """
        user_input = {
            'Countries Visited': ['african', 'east asia'],
            'Vector Exposure': ['insect bite (non- tick)'],
            'Symptoms': ['fever', 'rash'],
            ...
        }
        """

        results = []

        for _, row in self.df.iterrows():
            score = 0
            max_score = 0

            # Helper: fetch dataset field as list
            def get_list(field):
                return self._split_values(row.get(field, 'Unknown'))

            # Countries Visited (5)
            max_score += 5
            if self._match_any(user_input.get('Countries Visited', []), get_list('Countries Visited')):
                score += 5

            # Anatomy Involvement (5)
            max_score += 5
            if self._match_any(user_input.get('Anatomy Involvement', []), get_list('Anatomy Involvement')):
                score += 5

            # Vector Exposure (8)
            max_score += 8
            if 'other(including unknown)' in [x.lower() for x in user_input.get('Vector Exposure', [])]:
                score += 4  # half-credit for uncertainty
            elif self._match_any(user_input.get('Vector Exposure', []), get_list('Vector Exposure')):
                score += 8

            # Symptoms (10, proportional)
            if user_input.get('Symptoms'):
                max_score += 10
                n_user = len(user_input['Symptoms'])
                matches = sum(
                    1 for s in user_input['Symptoms']
                    if s.lower() in get_list('Symptoms')
                )
                if n_user > 0:
                    score += (10 / n_user) * matches

            # Duration of Illness (5)
            max_score += 5
            if self._match_any(user_input.get('Duration of Illness', []), get_list('Duration of Illness')):
                score += 5

            # Animal Contact (8)
            max_score += 8
            if self._match_any(user_input.get('Animal Contact Type', []), get_list('Animal Contact Type')):
                score += 8

            # Blood Film (15)
            max_score += 15
            user_blood = user_input.get('Blood Film Result', ['Unknown'])[0].lower()
            data_blood = get_list('Blood Film Result')
            if user_blood == 'unknown':
                pass
            elif user_blood == 'negative':
                if 'negative' in data_blood:
                    score += 0
                else:
                    score -= 10
            else:
                if any(x != 'negative' for x in data_blood):
                    score += 15

            # Immune Status (2)
            max_score += 2
            if self._match_any(user_input.get('Immune Status', []), get_list('Immune Status')):
                score += 2

            # Liver Function Tests (5)
            max_score += 5
            data_lft = get_list('Liver Function Tests')
            user_lft = user_input.get('Liver Function Tests', ['Unknown'])[0].lower()
            if 'variable' in data_lft or user_lft in data_lft:
                score += 5

            # Lab/clinical fields (5 each)
            lab_fields = [
                'Neurological Involvement', 'Eosinophilia', 'Fever',
                'Diarrhea', 'Bloody Diarrhea', 'Stool Cysts or Ova',
                'Anemia', 'High IgE Level'
            ]
            for field in lab_fields:
                max_score += 5
                data_vals = get_list(field)
                user_val = user_input.get(field, ['Unknown'])[0].lower()
                if 'variable' in data_vals and user_val != 'unknown':
                    score += 5
                elif user_val in data_vals:
                    score += 5

            # Cysts on Imaging (10)
            max_score += 10
            data_cyst = get_list('Cysts on Imaging')
            user_cyst = user_input.get('Cysts on Imaging', ['Unknown'])[0].lower()
            if user_cyst == 'negative':
                if 'negative' not in data_cyst:
                    score -= 5
            elif user_cyst != 'unknown':
                if any(x != 'negative' for x in data_cyst):
                    score += 10

            # --- Normalize and store ---
            likelihood = (score / max_score) * 100 if max_score > 0 else 0
            results.append({
                'Parasite': row['Parasite'],
                'Group': row.get('Group', ''),
                'Subtype': row.get('Subtype', ''),
                'Score': round(score, 2),
                'Max': round(max_score, 2),
                'Likelihood (%)': round(likelihood, 1),
                'Key Test': row.get('Key test', '')
            })

        # Sort results
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values(by='Likelihood (%)', ascending=False).reset_index(drop=True)

        return results_df

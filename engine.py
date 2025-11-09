import pandas as pd

# Sentinel used by the app to represent "not chosen" single-selects
SENTINEL = "__unset__"

class ParasiteIdentifier:
    """
    Scoring engine for ParAI-D.
    Iterates over the master dataframe rows and scores them against user input.
    """

    def __init__(self, df: pd.DataFrame):
        # Normalise columns and keep original df for reference
        self.df = df.copy()
        self.df.columns = [c.strip() for c in self.df.columns]

        # Normalise known optional Key Test column names
        if "Key Test" not in self.df.columns:
            for alt in ["Key test", "Key Tests", "Key notes", "Key Notes"]:
                if alt in self.df.columns:
                    self.df["Key Test"] = self.df[alt]
                    break
        if "Key Test" not in self.df.columns:
            self.df["Key Test"] = ""

        # Expose fixed max score (for Total Confidence)
        # Based on your latest weights: 5 + 5 + 8 + 10 + 5 + 8 + 15 + 2 + 5 + (8 binary *5) + 10 = 113
        self.max_possible_score = 113

    # --------------- helpers -----------------

    @staticmethod
    def _split(v):
        """Split semicolon-separated values to lower-cased list."""
        return [s.strip().lower() for s in str(v).split(";") if s and s.strip()]

    @staticmethod
    def _valid_user(val):
        """True only if user provided a meaningful value (not empty, not Unknown, not sentinel)."""
        if val is None:
            return False
        if isinstance(val, list):
            vals = [str(x).lower() for x in val if str(x).strip()]
            return any(x not in ("unknown", "choose…", "choose...", SENTINEL, "") for x in vals)
        v = str(val).lower()
        return v not in ("unknown", "choose…", "choose...", SENTINEL, "")

    @staticmethod
    def _match_any(user_vals, db_vals):
        """At least one user value matches any db value (lowercased)."""
        u = [str(x).lower() for x in user_vals if str(x).strip()]
        d = [str(x).lower() for x in db_vals if str(x).strip()]
        return any(x in d for x in u)

    # --------------- main scoring -----------------

    def score_entry(self, user_input: dict) -> pd.DataFrame:
        """
        Returns a DataFrame with columns:
        Parasite, Group, Subtype, Score, Likelihood (%), Key Test
        """
        out = []

        for _, row in self.df.iterrows():
            score = 0

            def gl(field):
                return self._split(row.get(field, ""))

            # Countries (5)
            if self._valid_user(user_input.get("Countries Visited", [])) and \
               self._match_any(user_input.get("Countries Visited", []), gl("Countries Visited")):
                score += 5

            # Anatomy (5)
            if self._valid_user(user_input.get("Anatomy Involvement", [])) and \
               self._match_any(user_input.get("Anatomy Involvement", []), gl("Anatomy Involvement")):
                score += 5

            # Vector (8) + special rule
            if self._valid_user(user_input.get("Vector Exposure", [])):
                vec = [x.lower() for x in user_input.get("Vector Exposure", [])]
                if vec == ["other(including unknown)"]:
                    score += 8
                elif self._match_any(vec, gl("Vector Exposure")):
                    score += 8

            # Symptoms (10) proportional to entries supplied
            ui_sy = user_input.get("Symptoms", [])
            if self._valid_user(ui_sy):
                db_sy = gl("Symptoms")
                matches = sum(1 for s in ui_sy if str(s).lower() in db_sy)
                score += (10 / max(1, len(ui_sy))) * matches

            # Duration (5)
            if self._valid_user(user_input.get("Duration of Illness", [])) and \
               self._match_any(user_input.get("Duration of Illness", []), gl("Duration of Illness")):
                score += 5

            # Animal contact (8)
            if self._valid_user(user_input.get("Animal Contact Type", [])) and \
               self._match_any(user_input.get("Animal Contact Type", []), gl("Animal Contact Type")):
                score += 8

            # Blood Film (15): Unknown/Choose ignored; negative mismatch = -10; any positive pattern = +15
            u_bf = [str(x).lower() for x in user_input.get("Blood Film Result", [])][:1] or [SENTINEL]
            db_bf = gl("Blood Film Result")
            if self._valid_user(u_bf):
                bf = u_bf[0]
                if bf == "negative":
                    if all(x != "negative" for x in db_bf):
                        score -= 10
                else:
                    if any(x != "negative" for x in db_bf):
                        score += 15

            # Immune status (2)
            if self._valid_user(user_input.get("Immune Status", [])) and \
               self._match_any(user_input.get("Immune Status", []), gl("Immune Status")):
                score += 2

            # LFT (5) with 'Variable' rule
            db_lft = gl("Liver Function Tests")
            u_lft = [str(x).lower() for x in user_input.get("Liver Function Tests", [])][:1] or [SENTINEL]
            if self._valid_user(u_lft):
                if "variable" in db_lft or u_lft[0] in db_lft:
                    score += 5

            # Binary fields (5 each) with Variable rule
            for f in [
                "Neurological Involvement", "Eosinophilia", "Fever",
                "Diarrhea", "Bloody Diarrhea", "Stool Cysts or Ova",
                "Anemia", "High IgE Level"
            ]:
                u = [str(x).lower() for x in user_input.get(f, [])][:1] or [SENTINEL]
                db = gl(f)
                if self._valid_user(u) and ("variable" in db or u[0] in db):
                    score += 5

            # Cysts on Imaging (10): Unknown/Choose ignored; negative mismatch = -5; any non-negative pattern = +10
            db_c = gl("Cysts on Imaging")
            u_c = [str(x).lower() for x in user_input.get("Cysts on Imaging", [])][:1] or [SENTINEL]
            if self._valid_user(u_c):
                cval = u_c[0]
                if cval == "negative":
                    if all(x != "negative" for x in db_c):
                        score -= 5
                else:
                    if any(x != "negative" for x in db_c):
                        score += 10

            out.append({
                "Parasite": row.get("Parasite"),
                "Group": row.get("Group"),
                "Subtype": row.get("Subtype"),
                "Score": score,
                "Likelihood (%)": round((score / self.max_possible_score) * 100, 2),
                "Key Test": row.get("Key Test", ""),
                "ref_row": row.to_dict()
            })

        res = pd.DataFrame(out).sort_values("Likelihood (%)", ascending=False).reset_index(drop=True)
        return res

    # --------------- user confidence (public util) -----------------

    def compute_user_confidence(self, ui: dict, row: pd.Series) -> float:
        """
        Compute percentage based ONLY on fields the user filled.
        Mirrors scoring rules but normalises to the max of only entered fields.
        """
        def gl(field):
            # pull from result row if provided, else from the stored ref_row
            return self._split(row.get(field, "") if field in row else row.get("ref_row", {}).get(field, ""))

        def match(u_list, field):
            ds = gl(field)
            u = [str(x).lower() for x in u_list if str(x).strip()]
            u = [x for x in u if x not in ("unknown", "choose…", "choose...", SENTINEL, "")]
            return any(x in ds for x in u)

        score = 0.0
        max_sc = 0.0

        # Countries (5)
        if self._valid_user(ui.get("Countries Visited", [])):
            max_sc += 5
            if match(ui["Countries Visited"], "Countries Visited"):
                score += 5

        # Anatomy (5)
        if self._valid_user(ui.get("Anatomy Involvement", [])):
            max_sc += 5
            if match(ui["Anatomy Involvement"], "Anatomy Involvement"):
                score += 5

        # Vector (8)
        if self._valid_user(ui.get("Vector Exposure", [])):
            max_sc += 8
            lower_vec = [x.lower() for x in ui["Vector Exposure"]]
            if lower_vec == ["other(including unknown)"]:
                score += 8
            elif match(ui["Vector Exposure"], "Vector Exposure"):
                score += 8

        # Symptoms (10)
        if self._valid_user(ui.get("Symptoms", [])):
            max_sc += 10
            db = gl("Symptoms")
            entered = [s for s in ui["Symptoms"] if str(s).strip()]
            m = sum(1 for s in entered if str(s).lower() in db)
            score += (10 / max(1, len(entered))) * m

        # Duration (5)
        if self._valid_user(ui.get("Duration of Illness", [])):
            max_sc += 5
            if match(ui["Duration of Illness"], "Duration of Illness"):
                score += 5

        # Animal (8)
        if self._valid_user(ui.get("Animal Contact Type", [])):
            max_sc += 8
            if match(ui["Animal Contact Type"], "Animal Contact Type"):
                score += 8

        # Blood Film (15)
        bf = [str(x).lower() for x in ui.get("Blood Film Result", [])][:1] or [SENTINEL]
        db_bf = gl("Blood Film Result")
        if self._valid_user(bf):
            max_sc += 15
            if bf[0] == "negative":
                if all(x != "negative" for x in db_bf):
                    score -= 10
            else:
                if any(x != "negative" for x in db_bf):
                    score += 15

        # Immune (2)
        if self._valid_user(ui.get("Immune Status", [])):
            max_sc += 2
            if match(ui["Immune Status"], "Immune Status"):
                score += 2

        # LFT (5)
        lft = [str(x).lower() for x in ui.get("Liver Function Tests", [])][:1] or [SENTINEL]
        if self._valid_user(lft):
            max_sc += 5
            db_l = gl("Liver Function Tests")
            if "variable" in db_l or lft[0] in db_l:
                score += 5

        # Binary (5 each)
        for f in [
            "Neurological Involvement", "Eosinophilia", "Fever",
            "Diarrhea", "Bloody Diarrhea", "Stool Cysts or Ova",
            "Anemia", "High IgE Level"
        ]:
            v = [str(x).lower() for x in ui.get(f, [])][:1] or [SENTINEL]
            if self._valid_user(v):
                max_sc += 5
                dbv = gl(f)
                if "variable" in dbv or v[0] in dbv:
                    score += 5

        # Cysts on Imaging (10)
        c = [str(x).lower() for x in ui.get("Cysts on Imaging", [])][:1] or [SENTINEL]
        db_c = gl("Cysts on Imaging")
        if self._valid_user(c):
            max_sc += 10
            if c[0] == "negative":
                if all(x != "negative" for x in db_c):
                    score -= 5
            else:
                if any(x != "negative" for x in db_c):
                    score += 10

        return (score / max_sc) * 100 if max_sc > 0 else 0.0

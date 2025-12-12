import numpy as np

class AlphaEngine:
    @staticmethod
    def get_direction_score(book_imbalance, flow_imbalance):
        """
        D = tanh(0.5 * I_book + 0.5 * I_flow)
        Returns a value between -1 and 1.
        """
        # Weighted combination
        combined = (0.5 * book_imbalance) + (0.5 * flow_imbalance)
        
        # Tanh activation for squashing
        score = np.tanh(combined)
        
        return score

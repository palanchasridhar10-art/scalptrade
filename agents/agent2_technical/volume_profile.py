from typing import Dict, Any, List
import pandas as pd
import numpy as np

class VolumeProfileEngine:
    def __init__(self, num_bins: int = 50, value_area_pct: float = 0.70):
        self.num_bins = num_bins
        self.value_area_pct = value_area_pct

    def analyze(self, df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        if df.empty or len(df) < 10:
            return {
                "poc": current_price,
                "vah": current_price,
                "val": current_price,
                "hvn_levels": [],
                "lvn_levels": [],
                "position_relative_to_va": "INSIDE"
            }

        min_price = float(df["low"].min())
        max_price = float(df["high"].max())
        
        if max_price <= min_price:
            return {
                "poc": current_price,
                "vah": current_price,
                "val": current_price,
                "hvn_levels": [],
                "lvn_levels": [],
                "position_relative_to_va": "INSIDE"
            }

        bins = np.linspace(min_price, max_price, self.num_bins)
        bin_volumes = np.zeros(self.num_bins - 1)

        # Distribute candle volume across bins
        for _, row in df.iterrows():
            c_low = row["low"]
            c_high = row["high"]
            c_vol = row["volume"]
            
            # Find overlapping bins
            mask = (bins[:-1] >= c_low) & (bins[1:] <= c_high)
            count = np.sum(mask)
            if count > 0:
                bin_volumes[mask] += c_vol / count
            else:
                # Assign to nearest bin
                mid = (c_low + c_high) / 2.0
                idx = np.clip(np.digitize(mid, bins) - 1, 0, len(bin_volumes) - 1)
                bin_volumes[idx] += c_vol

        # 1. Point of Control (POC)
        poc_idx = int(np.argmax(bin_volumes))
        poc_price = float((bins[poc_idx] + bins[poc_idx + 1]) / 2.0)

        # 2. Value Area (70% total volume around POC)
        total_vol = np.sum(bin_volumes)
        target_vol = total_vol * self.value_area_pct
        
        va_indices = {poc_idx}
        current_va_vol = bin_volumes[poc_idx]
        
        upper_idx = poc_idx + 1
        lower_idx = poc_idx - 1
        
        while current_va_vol < target_vol and (upper_idx < len(bin_volumes) or lower_idx >= 0):
            upper_vol = bin_volumes[upper_idx] if upper_idx < len(bin_volumes) else -1
            lower_vol = bin_volumes[lower_idx] if lower_idx >= 0 else -1
            
            if upper_vol >= lower_vol and upper_idx < len(bin_volumes):
                va_indices.add(upper_idx)
                current_va_vol += upper_vol
                upper_idx += 1
            elif lower_idx >= 0:
                va_indices.add(lower_idx)
                current_va_vol += lower_vol
                lower_idx -= 1
            else:
                break

        min_va_idx = min(va_indices)
        max_va_idx = max(va_indices)
        
        val_price = float(bins[min_va_idx])
        vah_price = float(bins[max_va_idx + 1])

        # 3. Position relative to Value Area
        if current_price > vah_price:
            pos_va = "ABOVE_VAH"
        elif current_price < val_price:
            pos_va = "BELOW_VAL"
        else:
            pos_va = "INSIDE_VA"

        # 4. HVN and LVN
        mean_vol = np.mean(bin_volumes)
        hvn_levels = [
            float((bins[i] + bins[i+1])/2.0) 
            for i in range(len(bin_volumes)) 
            if bin_volumes[i] >= mean_vol * 1.8
        ]
        lvn_levels = [
            float((bins[i] + bins[i+1])/2.0) 
            for i in range(len(bin_volumes)) 
            if bin_volumes[i] <= mean_vol * 0.3
        ]

        return {
            "poc": round(poc_price, 2),
            "vah": round(vah_price, 2),
            "val": round(val_price, 2),
            "hvn_levels": [round(x, 2) for x in hvn_levels[:4]],
            "lvn_levels": [round(x, 2) for x in lvn_levels[:4]],
            "position_relative_to_va": pos_va
        }

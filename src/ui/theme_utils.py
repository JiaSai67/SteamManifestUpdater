from qfluentwidgets import isDarkTheme

def get_state_color(state):
    dark = isDarkTheme()
    if state == "success":
        return "#6CCB5F" if dark else "#0F7B0F"  # Deeper green for light mode
    elif state == "error":
        return "#FF99A4" if dark else "#C42B1C"  # Win 11 standard error
    elif state == "warning":
        return "#FCE100" if dark else "#9D5D00"  # Dark amber for light mode
    elif state == "muted":
        return "#999999" if dark else "#5D5D5D"
    elif state == "accent":
        return "#a855f7" if dark else "#7e22ce"
    elif state == "text":
        return "#FFFFFF" if dark else "#000000"
    elif state == "text_muted":
        return "#888888" if dark else "#5D5D5D"
    elif state == "bg_stripe_1":
        return "#222222" if dark else "#F9F9F9"
    elif state == "bg_stripe_2":
        return "#2B2B2B" if dark else "#F0F0F0"
    return "#000000"

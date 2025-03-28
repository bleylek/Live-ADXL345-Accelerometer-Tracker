import dash
from dash import dcc, html
from dash.dependencies import Output, Input
import plotly.graph_objs as go
import serial
import json
import time
import threading

# -------------------------- Serial Port Setup --------------------------

ser = serial.Serial("COM3", 19200)
time.sleep(2)

ser.write(b'ACC_OFF\n')
time.sleep(2)
ser.write(b'ACC_ON\n')
print("ACC_ON komutu gönderildi. Veri bekleniyor...\n")

# -------------------------- Global Variables --------------------------

scale_factor = 0.016
t_vals, x_vals, y_vals, z_vals = [], [], [], []
vel_x, pos_x = [], []
counter = 0
offset = 0
offset_v = 0

# -------------------------- Serial Reading Thread --------------------------

def ema_filter(prev_ema, new_value, alpha=0.1):
    if prev_ema is None:
        return new_value
    return alpha * new_value + (1 - alpha) * prev_ema

def read_serial_data():
    global counter, ema_x, offset, offset_v
    ema_x = None
    max_len = 100
    dt = 0.05
    raw_x_vals = []

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                data = json.loads(line)

                if not isinstance(data, dict):
                    print("Geçersiz veri:", data)
                    return

                raw_x = int(data.get("x", 0))
                raw_y = int(data.get("y", 0))
                raw_z = int(data.get("z", 0))

                raw_x_vals.append(raw_x)
                if len(raw_x_vals) > 100:
                    raw_x_vals = raw_x_vals[-100:]
                if len(raw_x_vals) == 100:
                    offset = sum(raw_x_vals) / len(raw_x_vals)

                adjusted_x = raw_x - offset
                ema_x = ema_filter(ema_x, adjusted_x, alpha=0.1)
                filtered_x = ema_x

                if not x_vals or counter < 100:
                    x_vals.append(0)
                if -0.1 < x_vals[-1] < 0.1:
                    x_vals[-1] = 0

                if counter == 200:
                    offset_v = sum(vel_x) / len(vel_x) if vel_x else 0

                if not vel_x or counter < 100:
                    vel_x.append(0)
                else:
                    vel_x.append(vel_x[-1] + filtered_x * dt - offset_v)

                if not pos_x or counter < 200:
                    pos_x.append(0)
                else:
                    pos_x.append(pos_x[-1] + vel_x[-1] * dt)




                t_vals.append(counter)
                x_vals.append(filtered_x)
                y_vals.append(raw_y)
                z_vals.append(raw_z)

                counter += 1

                t_vals[:] = t_vals[-max_len:]
                x_vals[:] = x_vals[-max_len:]
                y_vals[:] = y_vals[-max_len:]
                z_vals[:] = z_vals[-max_len:]
                vel_x[:] = vel_x[-max_len:]
                pos_x[:] = pos_x[-max_len:]

        except Exception as e:
            print("Hata:", e)
            break

thread = threading.Thread(target=read_serial_data, daemon=True)
thread.start()

# -------------------------- Dash App Setup --------------------------

app = dash.Dash(__name__)
app.title = "Gerçek Zamanlı ADXL345 Verisi"

app.layout = html.Div([
    html.H2("Gerçek Zamanlı ADXL345 İvme Verileri", style={"textAlign": "center"}),

    dcc.Graph(id='live-graph'),

    html.Div(id='distance-output', style={'textAlign': 'center', 'fontSize': 24, 'marginTop': '20px'}),

    dcc.Interval(id='interval-component', interval=100, n_intervals=0),
])

# -------------------------- Callback --------------------------

@app.callback(
    Output('live-graph', 'figure'),
    Output('distance-output', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_graph(n):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t_vals, y=x_vals, mode='lines', name='X', line=dict(color='red')))
    fig.add_trace(go.Scatter(x=t_vals, y=vel_x, mode='lines', name='V', line=dict(color='orange')))
    fig.add_trace(go.Scatter(x=t_vals, y=pos_x, mode='lines', name='Position', line=dict(color='blue')))

    fig.update_layout(
        xaxis_title='Örnek',
        yaxis_title='Değer',
        yaxis=dict(range=[-10, 10]),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(x=0, y=1),
        template='plotly_white'
    )

    distance_str = f"Toplam Alınan Yol (X yönü): {pos_x[-1]:.2f} birim" if pos_x else "Veri bekleniyor..."
    return fig, distance_str

# -------------------------- Run --------------------------

if __name__ == '__main__':
    try:
        app.run()
    finally:
        ser.write(b'ACC_OFF\n')
        time.sleep(2)
        ser.close()

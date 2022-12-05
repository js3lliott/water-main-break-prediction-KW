import pandas as pd
from flask import Flask, jsonify, request
import pickle

# load model
model = pickle.load(open('rf_model.pkl', 'rb'))

# app
app = Flask(__name__)

# routes
@app.route('/', methods=['POST'])

def predict():
    # get data
    data = request.get_json(force=True)
    
    # convert data into dataframe
    data.update((x, [y]) for x, y in data.items())
    data_df = pd.DataFrame.from_dict(data)
    
    # predictions
    result = model.predict(data_df)
    
    # predictions
    output = {'results': float(result)}
    
    # return data
    return jsonify(results=output)

if __name__ == '__main__':
    app.run(port=5000, debug=True)
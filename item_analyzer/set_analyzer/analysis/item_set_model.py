import sklearn
from sklearn import tree
from sklearn import linear_model
from sklearn import cross_validation, preprocessing
from sklearn.metrics import r2_score, explained_variance_score, mean_absolute_error, mean_squared_error, median_absolute_error
from sklearn.externals import joblib

from set_analyzer.models import *

import numpy as np

from django.conf import settings

import os, pickle

#IDEA
#Machine learning model to make the data smooth and continuous
#   -> sklearn
#Simulated annealing or other similar algorithm to solve for the local maximum
#   -> scipy.optimize.basinhopping

class ItemSetModel(object):
    """docstring for ItemSetModel"""

    clf = None

    MODEL_PATH = os.path.join(settings.BASE_DIR, 'set_analyzer', 'analysis', 'models')
    CACHE_FILE = os.path.join(MODEL_PATH, 'model_cache.cache')

    def __init__(self):
        super(ItemSetModel, self).__init__()
        #self.clf = tree.DecisionTreeRegressor()
        self.clf = linear_model.Lasso(0.1)

    def get_data_sets(self, cache=False, **kwargs):
        """
        Data Schema:
            Input:
                1    My champion ID
                5    [Other team's champion ID's]
                7    [7 Final Items]
                5    [first 5 items purchased]
                ________________________________________
                18 features

            Output:
                Score = A(Gold/time) + B(xp/time) + C(win)
                ________________________________________
                1 Output

        """
        matches = Match.objects.all(**kwargs)

        #Presize data
        features = 18
        outputs = 1
        num_participants = len(matches)*10
        input_data = np.zeros((num_participants, features))
        output_data = np.zeros((num_participants, outputs))

        row_num = 0

        get_champ_id = lambda x : x.champion.champion_id
        diff_team = lambda x , y : x.team_id != y.team_id
        item_purchased = lambda x: x.event_type == "ITEM_PURCHASED"

        #Iterate over every match in the database
        for match in matches:

            #Prefetch users and teams
            team_map = {}
            team_data = np.zeros((2,5))
            count = 0
            for tag in match.teams:
                team_map[int(tag)] = count
                count+=1

            team_indices = dict.fromkeys(team_map, 0)

            for ind,p in enumerate(match.participants.values()):
                team_data[team_map[p.team_id]][team_indices[p.team_id]] = get_champ_id(p)
                team_indices[p.team_id] += 1

            #Iterate over every user in the match
            for pid, participant in match.participants.items():
                col_num = 0

                #My ID
                input_data[row_num][col_num] = get_champ_id(participant)
                col_num+=1

                #Other Team's champion ID's
                if(team_map[participant.team_id] == 0):
                    input_data[row_num][col_num:col_num+5] = team_data[1,:]
                else:
                    input_data[row_num][col_num:col_num+5] = team_data[0,:]

                col_num+=5

                #My items
                for item_id in participant.final_build:
                    input_data[row_num][col_num] = item_id
                    col_num+=1

                #My Item purchases
                count = 0
                for item_purchase in (x for x in participant.item_events if item_purchased(x)):
                    if(count==5):
                        break
                    input_data[row_num][col_num] = item_purchase.payload['itemId']
                    col_num += 1
                    count += 1


                #Score
                #   Assume that average gold/sec is ~8
                #   Assume that average kda is ~2.6
                #   Have a game win worth 1.5 times score
                score = (participant.kda()*3 + participant.gold_earned/match.duration) * (1.5 if match.teams[str(participant.team_id)].won else 1.0)
                output_data[row_num][0] = score

                row_num+=1

        if(cache):
            print('Caching data...')
            self.cache_data((input_data, output_data))

        return (input_data, output_data)

    def cache_data(self, data):
        with open(self.CACHE_FILE, 'wb') as f:
            pickle.dump(data, f)

    def get_cached_data(self):
        with open(self.CACHE_FILE, 'rb') as f:
            return pickle.load(f)

    def train(self, X, Y, train_ratio=1, **kwargs):

        print("Training model...")
        if(train_ratio==1):
            self.clf.fit(X,Y)
        else:
            n = len(X)
            tn = int(n*train_ratio)
            self.clf.fit(X[:tn,:],Y[:tn,:])
            print("Evaluating model...")
            evaluate_fit(self.clf, X[tn:,:],Y[tn:,:])

    def predict(self, X):
        return self.clf.predict(X)

    #MODEL EVAUATION
    def k_fold(self, folds, **kwargs):
        X, Y = self.get_data_sets(**kwargs)
        k_fold_evaluate(self.clf, X, y, folds)

    #LOAD AND SAVE
    def save(self, filename):
        path = os.path.join(self.MODEL_PATH, filename)
        joblib.dump(self.clf, path)

    def load(self, filename):
        path = os.path.join(self.MODEL_PATH, filename)
        self.clf = joblib.load(path)

#MODEL EVAUATION
def k_fold_evaluate(clf, X, y, folds):
    print("Running K-Folding: {} folds on {} rows".format(folds, len(X)))
    this_scores = cross_validation.cross_val_score(self.model, X, y, n_jobs=-1, cv=folds)
    print("k_folding results: {}\n".format(this_scores))

def evaluate_fit(clf, X, Y):
    predicted_data = clf.predict(X)
    print("Model R squared: {}".format(r2_score(Y, predicted_data)))
    print("Model explained_variance_score: {}".format(explained_variance_score(Y, predicted_data)))
    print("Model mean_squared_error: {}".format(mean_squared_error(Y, predicted_data)))

def chi_squared(m, y, v):
    """My own R^2 check"""
    y_var = np.var(y)
    t = 0
    for i in range(v):
        t += (y[i] - m[i])**2
    return 1 - t / y_var / v

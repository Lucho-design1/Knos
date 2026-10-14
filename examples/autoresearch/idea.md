# idea.md

The baseline is a linear logistic regression on the raw features. I suspect the label depends on squares and
products of the features (distance from a centre, an interaction), which a linear model cannot see. Try richer
features first, then tune the optimiser (learning rate, epochs, scaling, regularisation).

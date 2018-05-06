from numba import jit
import numpy as np


def sparsewarp(_X, _Y, trials, xtst):
    """

    Parameters
    ----------
    X : x coordinates of knots for each trial (shape: n_trials x n_knots)
    Y : y coordinates of knots for each trial (shape: n_trials x n_knots)
    trials : int trial id for each coordinate (shape: n_trials)
    xtst : queried x coordinate for each trial (shape: n_trials)

    Note:
        X is assumed to be sorted along axis=1

    Returns
    -------
    ytst : interpolated y value for each x in xtst (shape: trials)
    """
    X = _X[trials]
    Y = _Y[trials]

    # allocate result
    ytst = np.empty_like(xtst)

    # for each trial (row of X) find first knot larger than test point
    p = np.argmin(xtst[:, None] > X, axis=1)

    # make sure that we never try to interpolate to the left of
    # X[:,0] to avoid out-of-bounds error. Test points requiring
    # extrapolation are clipped (see below).
    np.maximum(1, p, out=p)

    # indexing vector along trials (used to index with p)
    k = np.arange(len(p))

    # distance between adjacent knots
    dx = np.diff(_X, axis=1)[trials]

    # fractional distance of test points between knots
    lam = (xtst - X[k, p-1]) / dx[k, p-1]

    # linear interpolation
    ytst = (Y[k, p-1]*(1-lam)) + (Y[k, p]*(lam))

    # clip test values below X[:, 0] or above X[:, -1]
    idx = lam > 1
    ytst[idx] = Y[idx, -1]
    idx = lam < 0
    ytst[idx] = Y[idx, 0]

    return ytst


# @jit(nopython=True)
def densewarp(X, Y, data, out):

    K = data.shape[0]
    T = data.shape[1]
    n_knots = X.shape[1]

    for k in range(K):

        # initialize line segement for interpolation
        y0 = Y[k, 0]
        x0 = X[k, 0]
        slope = (Y[k, 1] - Y[k, 0]) / (X[k, 1] - X[k, 0])

        # 'n' counts knots in piecewise affine warping function.
        n = 1

        # iterate over all time bins, stop early if loss is too high.
        for t in range(T):

            # update interpolation point
            while (t/(T-1) > X[k, n]) and (n < n_knots-1):
                y0 = Y[k, n]
                x0 = X[k, n]
                slope = (Y[k, n+1] - y0) / (X[k, n+1] - x0)
                n += 1

            z = y0 + slope*((t/(T-1)) - x0)

            if z < 0:
                out[k, t] = np.nan  # data[k, 0]
            elif z > 1:
                out[k, t] = np.nan  # data[k, -1]
            else:
                foo = True
                _i = z * (T-1)
                rem = _i % 1
                i = int(_i)
                out[k, t] = (1-rem) * data[k, i] + rem * data[k, i+1]

    return out


@jit(nopython=True)
def warp_with_loss(xtst, X, Y, warps, template, new_loss, last_loss, data, neurons, lossfunc):

    # number of interpolated points
    T = len(xtst)

    # number discontinuities in piecewise linear function
    N = len(X[0])

    # normalizing divisor for average loss across each trial
    denom = data.shape[1] * data.shape[2]

    # iterate over trials
    for i in range(len(X)):

        # initialize line segement for interpolation
        y0 = Y[i, 0]
        x0 = X[i, 0]
        slope = (Y[i, 1] - Y[i, 0]) / (X[i, 1] - X[i, 0])

        # 'm' counts the timebins within trial 'i'.
        # 'n' counts knots in piecewise affine warping function.
        m = 0
        n = 1

        # compute loss for trial i
        new_loss[i] = 0

        # iterate over all time bins, stop early if loss is too high.
        while (m < T) and (new_loss[i] < last_loss[i]):

            # update interpolation point
            while (n < N-1) and (m/(T-1) > X[i, n]):
                y0 = Y[i, n]
                x0 = X[i, n]
                slope = (Y[i, n+1] - y0) / (X[i, n+1] - x0)
                n += 1

            # do interpolation and move on to next element in xtst
            z = y0 + slope*(xtst[m] - x0)

            # clip warp interpolation between zero and one
            if z < 0:
                warps[i, m] = 0.0
                pred = template[0]

            elif z > 1:
                warps[i, m] = 1.0
                pred = template[-1]

            else:
                warps[i, m] = z
                _j = z * (T-1)
                rem = _j % 1
                j = int(_j)
                pred = (1-rem)*template[j] + rem*template[j+1]

            new_loss[i] += lossfunc(pred, data[i, m]) / denom

            # move to next timepoint
            m += 1

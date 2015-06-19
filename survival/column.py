import logging

import numpy
import pandas

from pandas.core.common import is_categorical_dtype

__all__ = ['encode_categorical', 'categorical_to_numeric']


def _apply_along_column(array, func1d, **kwargs):
    if isinstance(array, pandas.DataFrame):
        return array.apply(func1d, **kwargs)
    else:
        return numpy.apply_along_axis(func1d, 0, array, **kwargs)


def standardize_column(series_or_array, with_std=True):
    d = series_or_array.dtype
    if issubclass(d.type, numpy.number):
        m = series_or_array.mean()
        series_or_array -= m

        if with_std:
            s = series_or_array.std()
            series_or_array /= s

    return series_or_array


def standardize(table, with_std=True):
    """
    Perform Z-Normalization on each numeric column of the given table

    Parameters
    ----------
    table : pandas.DataFrame or numpy.ndarray
        Data to standardize.

    with_std : bool, default=True
        If ``False`` data is only centered and not converted to unit variance..
    """
    if isinstance(table, pandas.DataFrame):
        cat_columns = table.select_dtypes(include=['category']).columns
    else:
        cat_columns = []

    new_frame = _apply_along_column(table, standardize_column, with_std=with_std)

    # work around for apply converting category dtype to object
    # https://github.com/pydata/pandas/issues/9573
    for col in cat_columns:
        new_frame[col] = table[col].copy()

    return new_frame


def _encode_categorical_series(series, allow_drop=True):
    values = _get_dummies_1d(series, allow_drop=allow_drop)
    if values is None:
        return

    enc, levels = values
    if enc is None:
        return pandas.Series(index=series.index, name=series.name, dtype=series.dtype)

    names = []
    for key in range(1, enc.shape[1]):
        names.append(series.name + "=" + levels[key])
    series = pandas.DataFrame(enc[:, 1:], columns=names, index=series.index)

    return series


def encode_categorical(table, **kwargs):
    """
    Encode categorical columns with M categories into M-1 column according tot he one-hot scheme
    """

    if isinstance(table, pandas.Series):
        return _encode_categorical_series(table, **kwargs)
    else:
        new_table = pandas.DataFrame(index=table.index)

        for j in range(table.shape[1]):
            series = table.iloc[:, j]

            # for columns containing categories
            if is_categorical_dtype(series.dtype) or series.dtype.char == "O":
                series = _encode_categorical_series(series, **kwargs)
                if series is None:
                    continue

            # join tables on index
            new_table = new_table.join(series)
        return new_table


def _get_dummies_1d(data, allow_drop=True):
    # Series avoids inconsistent NaN handling
    cat = pandas.Categorical.from_array(pandas.Series(data))
    levels = cat.categories
    number_of_cols = len(levels)

    # if all NaN or only one level
    if allow_drop and number_of_cols < 2:
        logging.getLogger(__package__).warning(
            "dropped categorical variable '{0}', because it has only {1} values".format(data.name, number_of_cols))
        return
    elif number_of_cols == 0:
        return None, levels

    dummy_mat = numpy.eye(number_of_cols).take(cat.codes, axis=0)

    # reset NaN GH4446
    dummy_mat[cat.codes == -1] = numpy.nan

    return dummy_mat, levels


def categorical_to_numeric(table):

    def transform(column):
        if is_categorical_dtype(column.dtype):
            return column.cat.codes
        if column.dtype.char == "O":
            try:
                nc = column.astype(int)
            except ValueError:
                classes = column.dropna().unique()
                classes.sort(kind="mergesort")
                nc = column.replace(classes, numpy.arange(classes.shape[0]))
            return nc
        elif column.dtype == bool:
            return column.astype(int)

        return column

    if isinstance(table, pandas.Series):
        return pandas.Series(transform(table), name=table.name, index=table.index)
    else:
        return table.apply(transform, axis=0, reduce=False)

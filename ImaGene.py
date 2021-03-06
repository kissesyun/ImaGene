
### ------------- utilities --------------------


def extract_msms_parameter(line, option, position=0):
    """
    Extract simulation parameters from first line of msms file

    Keyword Arguments:
        line (string) -- first line of (gzipped) msms file in bytes format 
        option (string) -- switch of msms to match
        position (int) -- i-th value to be taken after the switch

    Return:
        parameter (string)
    """

    return line.partition(option)[2].split()[position]


def get_index_classes(targets, classes):
    """
    Get index array for targets corresponding to selected classes

    Keyword Arguments:
        targets (array) -- target feature in ImaGene object
        classes (array) -- classes to select from targets

    Return:
        index (array)
    """
    index = []
    for counter,value in enumerate(classes):
        index = np.concatenate([index, np.where(targets==value)[0]])
    return np.asarray(index, dtype='int')


def get_index_random(genes=[], length=0):
    """
    Get random index array

    Keyword Arguments:
        length (int) -- length random index array
        genes (object) -- ImaGene object

    Return:
        index (array)
    """
    if length == 0:
        length = len(genes.data)
    if length == 0:
        print('Either length or genes must be provided.')
    return np.random.permutation(length)


def calculate_allele_frequency(genes, position):
    """
    ...
    """
    return [np.where(genes.data[i][:,np.where(genes.positions[i]==position)[0][0],0]==255,1,0).sum() for i in range(len(genes.data))]


def to_binary(targets):
    return np.asarray(np.where(targets == targets.min(), 0, 1).astype('float32'))


def to_categorical(targets, wiggle=0, sd=0):
    classes = np.unique(targets)
    nr_classes = len(classes)
    results = np.zeros((len(targets), len(classes)), dtype='float32')
    for counter, value in enumerate(targets):
        index = np.where(classes == value)[0]
        # add wiggle (if any)
        if wiggle > 0:
            index += np.random.randint(low=-wiggle, high=wiggle+1)
            if index < 0:
                index = 0
            elif index >= results.shape[1]:
                index = results.shape[1] - 1
        results[counter, index] = 1.
        # add sd (if any)
        if sd > 0:
            probs = scipy.stats.norm.pdf(range(nr_classes), loc=index, scale=sd)
            results[counter, ] = probs / probs.sum()
            del probs
    return results

def load_imagene(file):
    """
    Load ImaGene object
    """
    with open(file, 'rb') as fp:
        gene = pickle.load(fp)
    return gene

def load_imanet(file):
    """
    Load ImaNet object
    """
    with open(file, 'rb') as fp:
        net = pickle.load(fp)
    return net


### -------- objects ------------------

class ImaFile:
    """
    Parser for real data and simulations
    """
    def __init__(self, simulations_folder, nr_samples, model_name='N/A'):
        self.simulations_folder = simulations_folder
        self.nr_samples = nr_samples
        self.model_name = model_name
        return None

    def extract_description(self, file_name, first_line):
        """
        Read first line of simulations, extract all metadata and store it in a dictionary

        Keyword Arguments:
            file_name (string) -- name of simulation file
            first_line (string) -- first line of gzipped msms file
            model_name (string) -- name of demographic model

        Return:
            description (string)
        """

        desc = {'name':file_name}

        # Extracting parameters
        desc.update({'Nref':int(extract_msms_parameter(first_line, '-N '))})
        desc.update({'nr_chroms':int(extract_msms_parameter(first_line, '-N ', 1))})
        desc.update({'nr_replicates':int(extract_msms_parameter(first_line, '-N ', 2))})

        desc.update({'mutation_rate':float(extract_msms_parameter(first_line, '-t '))})
        desc.update({'recombination_rate':float(extract_msms_parameter(first_line, '-r '))})
        desc.update({'recombination_rate_nr_sites':int(extract_msms_parameter(first_line, '-r ', 1))})

        desc.update({'selection_position':float(extract_msms_parameter(first_line, '-Sp '))})
        desc.update({'selection_start_time':float(extract_msms_parameter(first_line, '-SI '))})
        desc.update({'selection_start_frequency':float(extract_msms_parameter(first_line, '-SI ', 2))})
    
        desc.update({'selection_coeff_HOMO':int(extract_msms_parameter(first_line, '-SAA '))})
        desc.update({'selection_coeff_hetero':int(extract_msms_parameter(first_line, '-SAa '))})
        desc.update({'selection_coeff_homo':int(extract_msms_parameter(first_line, '-Saa '))})

        desc.update({'model':str(self.model_name)})

        # Get the UNIX Time Stamp of when the file was modification
        desc.update({'modification_stamp':os.stat(file_name).st_mtime})

        # Allow deleted files to be tracked in json folder
        desc.update({'active':'active'})

        return desc

    def read_simulations(self, parameter_name='selection_coeff_hetero', max_nrepl=None, verbose=0):
        """
        Read simulations and store into compressed numpy arrays

        Keyword Arguments:
            simulations_folder: folder with simulation files

        Returns:
            an object of class Genes
        """

        data = []
        positions = []
        description = []

        # Open the directory in which simulation files are stored
        for file_name in os.listdir(self.simulations_folder):

            full_name = self.simulations_folder + '/%s' %(file_name)

            if verbose > 0:
                print(full_name, ': ', end='')

            # Read lines including the metadata
            f = gzip.open(full_name, 'rb')
            file_content = f.read().decode('utf8').split('\n')

            # Search the // char inside the file
            starts = ([i for i, e in enumerate(file_content) if e == '//'])

            # limit the scan to the first max_nrepl items (if set)
            if max_nrepl!=None:
                starts = starts[:max_nrepl]

            if verbose > 0:
                print(len(starts))

            # Populate object with data for each simulated gene
            for idx, pointer in enumerate(starts):

                # Description for each simulation
                description.append(self.extract_description(full_name, file_content[0]))

                nr_columns = int(file_content[pointer+1].split('segsites: ')[1])
                haplotypes = np.zeros((self.nr_samples, nr_columns, 1), dtype='uint8')
                pos = file_content[pointer+2].split(' ')
                pos.pop()
                pos.pop(0)
                positions.append(np.asarray(pos, dtype='float32'))
                del pos

                for j in range(self.nr_samples):

                    hap = list(file_content[pointer + 3 + j])

                    # string processing: if not 0/1 --> convert to 1
                    hap = ['1' if element!='0' and element!=1 else element for element in hap]
                    # switch colours, 1s are black and 0s are white
                    hap = ['255' if element=='1' else element for element in hap]
                    haplotypes[j,:,0] = hap

                data.append(haplotypes)

            f.close()

        gene = ImaGene(data=data, positions=positions, description=description, parameter_name=parameter_name)

        return gene


class ImaGene:
    """
    A batch of genomic images
    """
    def __init__(self, data, positions, description, targets=[], parameter_name=None, classes=[]):
        self.data = data
        self.positions = positions
        self.description = description
        self.dimensions = (np.zeros(len(self.data)), np.zeros(len(self.data)))
        self.parameter_name = parameter_name # this is passed by ImaFile.read_simulations()
        self.targets = np.zeros(len(self.data), dtype='int32')
        for i in range(len(self.data)):
            # set targets from file description
            self.targets[i] = self.description[i][self.parameter_name]
            # assign dimensions
            self.dimensions[0][i] = self.data[i].shape[0]
            self.dimensions[1][i] = self.data[i].shape[1]
        self.classes = np.unique(self.targets)
        return None

    def summary(self):
        """
        Prints general info on the object.

        Keyword Arguments:


        Returns:
            0
        """
        nrows = self.dimensions[0]
        ncols = self.dimensions[1]
        print('An object of %d images' % len(self.data))
        print('Rows: min %d, max %d, mean %f, std %f' % (nrows.min(), nrows.max(), nrows.mean(), nrows.std()))
        print('Columns: min %d, max %d, mean %f, std %f' % (ncols.min(), ncols.max(), ncols.mean(), ncols.std()))
        return 0

    def plot(self, index):
        """
        Plot one image in gray scale.

        Keyword arguments:
            index: index of image to plot

        Returns:
            0
        """
        image = plt.imshow(self.data[index][:,:,0], cmap='gray')
        plt.show(image)
        return 0

    def majorminor(self):
        """
        Convert to major/minor polarisation.

        Keyword Arguments:

        Returns:
            0
        """
        for i in range(len(self.data)):
            idx = np.where(np.mean(self.data[0][:,:,0]/255., axis=0) > 0.5)[0]
            self.data[0][:,idx,0] = 255 - self.data[0][:,idx,0]
        return 0

    def filter_freq(self, minimal_maf, verbose=0):
        """
        Remove sites whose minor allele frequency is below the set threshold.

        Keyword Arguments:
            minimal_maf: minimal minor allele frequency to retain the site

        Returns:
            0
        """
        for i in range(len(self.data)):
            idx = np.where(np.mean(self.data[i][:,:,0]/255., axis=0) >= minimal_maf)[0]
            self.positions[i] = self.positions[i][idx]
            self.data[i] = self.data[i][:,idx,:]
            # update nr of columns in dimensions
            self.dimensions[1][i] = self.data[i].shape[1]
        return 0

    def resize(self, dimensions=(128, 128), option=None, set_to_boundaries=True):
        """
        Resize all images to same dimensions.

        Keyword Arguments:
            dimensions: tuple, nr of rows and nr of columns
            option: either 'mean', 'min' or 'max'
            set_to_boundaries: if True, all cells are pushed up/down to 255/0

        Returns:
            0
        """
        if option == 'mean':
            dimensions = (int(self.dimensions[0].mean()), int(self.dimensions[1].mean()))
        elif option == 'min':
            dimensions = (int(self.dimensions[0].min()), int(self.dimensions[1].min()))
        elif option == 'max':
            dimensions = (int(self.dimensions[0].max()), int(self.dimensions[1].max()))
        else: pass
        for i in range(len(self.data)):
            image = np.copy(self.data[i][:,:,0])
            self.data[i] = np.zeros((dimensions[0], dimensions[1], 1), dtype='uint8')
            self.data[i][:,:,0] = (skimage.transform.resize(image, dimensions, anti_aliasing=True, mode='reflect')*255).astype('uint8')
            del image
            # reassign data dimensions
            self.dimensions[0][i] = self.data[i].shape[0]
            self.dimensions[1][i] = self.data[i].shape[1]
            if set_to_boundaries == True:
                self.data[i] = (np.where(self.data[i] < 128, 0, 255)).astype('uint8')
        return 0

    def sort(self, ordering):
        """
        Sort rows and/or columns given an ordering.

        Keyword Arguments:
            ordering: either 'rows_freq', 'cols_freq', 'rows_dist', 'cols_dist'

        Returns:
            0
        """
        if ordering == 'rows_freq':
            for i in range(len(self.data)):
                uniques, counts = np.unique(self.data[i], return_counts=True, axis=0)
                counter = 0
                for j in counts.argsort()[::-1]:
                    for z in range(counts[j]):
                        self.data[i][counter,:,:] = uniques[j,:,:]
                        counter += 1
        elif ordering == 'cols_freq':
            for i in range(len(self.data)):
                uniques, counts = np.unique(self.data[i], return_counts=True, axis=1)
                counter = 0 #
                for j in counts.argsort()[::-1]:
                    for z in range(counts[j]):
                        self.data[i][:,counter,:] = uniques[:,j,:]
                        counter += 1
        elif ordering == 'rows_dist':
            for i in range(len(self.data)):
                uniques, counts = np.unique(self.data[i], return_counts=True, axis=0)
                # most frequent row in float
                top = uniques[counts.argsort()[::-1][0]].transpose().astype('float32')
                # distances from most frequent row
                distances = np.mean(np.abs(uniques[:,:,0] - top), axis=1)
                # fill in from top to bottom
                counter = 0
                for j in distances.argsort():
                    for z in range(counts[j]):
                        self.data[i][counter,:,:] = uniques[j,:,:]
                        counter += 1
        elif ordering == 'cols_dist':
            for i in range(len(self.data)):
                uniques, counts = np.unique(self.data[i], return_counts=True, axis=1)
                # most frequent column
                top = uniques[:,counts.argsort()[::-1][0]].astype('float32')
                # distances from most frequent column
                distances = np.mean(np.abs(uniques[:,:,0] - top), axis=0)
                # fill in from left to right
                counter = 0
                for j in distances.argsort():
                    for z in range(counts[j]):
                        self.data[i][:,counter,:] = uniques[:,j,:]
                        counter += 1
        else:
            print('Select a valid ordering.')
            return 1
        return 0

    def convert(self, normalise=False, flip=True, verbose=False):
        """
        Check for correct data type and convert otherwise. Convert to float numpy arrays [0,1] too. If flip true, then flips 0-1
        """
        # if list, put is as numpy array
        if type(self.data) == list:
            if len(np.unique(self.dimensions[0]))*len(np.unique(self.dimensions[1])) == 1:
                if verbose:
                    print('Converting to numpy array.')
                self.data = np.asarray(self.data)
            else:
                print('Aborted. All images must have the same shape.')
                return 1
        # if unit8, put it as float and divide by 255
        if self.data.dtype == 'uint8':
            if verbose:
                print('Converting to float32.')
            self.data = self.data.astype('float32')
        if self.data.max() > 1:
            if verbose:
                print('Converting to [0,1].')
            self.data /= 255.
        # normalise
        if normalise==True:
            if verbose:
                print('Normalising samplewise.')
            for i in range(len(self.data)):
                mean = self.data[i].mean()
                std = self.data[i].std()
                self.data[i] -= mean
                self.data[i] /= std
        # flip
        if flip==True:
            if verbose:
                print('Flipping values.')
            for i in range(len(self.data)):
                self.data[i] = 1. - self.data[i]
        if verbose:
            print('A numpy array with dimensions', self.data.shape, 'and', len(self.targets), 'targets and', len(self.classes), 'classes.')
        return 0

    def set_classes(self, classes=[], nr_classes=0):
        """
        Set classes (or reinitiate)
        """
        # at each call reinitialise for safety
        targets = np.zeros(len(self.data), dtype='int32')
        for i in range(len(self.data)):
            # set target from file description
            targets[i] = self.description[i][self.parameter_name]
        self.classes = np.unique(targets)
        # calculate and/or assign new classes
        if nr_classes > 0:
            self.classes = np.asarray(np.linspace(targets.min(), targets.max(), nr_classes), dtype='int32')
        elif len(classes)>0:
            self.classes = classes
        del targets
        return 0

    def set_targets(self):
        """
        Set targets for binary or categorical classification (not for regression) AFTER running set_classes
        """
        # initialise
        self.targets = np.zeros(len(self.data), dtype='int32')
        for i in range(len(self.targets)):
            # reinitialise
            self.targets[i] = self.description[i][self.parameter_name]
            # assign label as closest class
            self.targets[i] = self.classes[np.argsort(np.abs(self.targets[i] - self.classes))[0]]
        return 0

    def subset(self, index):
        """
        Subset object to index array (for shuffling or only for multiclassification after setting classes and targets)
        """
        # update based on index
        self.targets = self.targets[index]
        self.data = self.data[index]
        self.positions = [self.positions[i] for i in index]
        self.description = [self.description[i] for i in index]
        for i in range(len(self.data)):
            self.dimensions[0][i] = self.data[i].shape[0]
            self.dimensions[1][i] = self.data[i].shape[1]
        return 0

    def save(self, file):
        """
        Save to file
        """
        with open(file, 'wb') as fp:
            pickle.dump(self, fp)
        return 0


class ImaNet:
    """
    Training and Learning
    """
    def __init__(self, name=None, model=None):
        self.name = name
        self.scores = {'val_loss': [], 'val_acc': [], 'loss': [], 'acc': [], 'val_mse': [], 'val_mae': [], 'mse': [], 'mae': []}
        self.test = np.zeros(2)
        self.values = None # matrix(3,nr_test) true, map, mle
        return None

    def update_scores(self, score):
        """
        Append new scores after each training
        """
        for key in self.scores.keys():
            if key in score.history:
                self.scores[key].append(score.history[key])
        return 0

    def plot_train(self, file=None):
        """
        Plot training accuracy/mae and loss/mse
        """
        if 'loss' in self.scores.keys():
            loss = self.scores['loss']
            val_loss = self.scores['val_loss']
            acc = self.scores['acc']
            val_acc = self.scores['val_acc']
        else:
            loss = self.scores['mse']
            val_loss = self.scores['val_mse']
            acc = self.scores['mae']
            val_acc = self.scores['val_mae']
        epochs = range(1, len(loss) + 1)

        plt.figure()

        plt.subplot(211)

        plt.plot(epochs, loss, 'bo', label='Training loss/mse')
        plt.plot(epochs, val_loss, 'b', label='Validation loss/mse')
        plt.title('Training and validation loss/mse')
        plt.legend()

        plt.subplot(212)

        plt.plot(epochs, acc, 'bo', label='Training acc/mae')
        plt.plot(epochs, val_acc, 'b', label='Validation acc/mae')
        plt.title('Training and validation accuracy/mae')
        plt.legend()

        if file==None:
            plt.show()
        else:
            plt.savefig(file)

        return 0

    def predict(self, gene, model):
        """
        Calculate predicted values (many, I assume this is for testing not for single prediction); output is a matrix with rnows=2, row 0 is true, row 1 is MAP, row 2 is posterior mean
        """
        self.values = np.zeros((3, gene.data.shape[0]), dtype='float32')
        if len(gene.targets.shape) == 1:
            probs = model.predict(gene.data, batch_size=None)[:,0]
            self.values[1,:] = np.where(probs < 0.5, 0., 1.)
            self.values[0,:] = gene.targets
            self.values[2,:] = [np.average(gene.classes, weights=probs[i]) for i in range(probs.shape[0])]
        else:
            probs = model.predict(gene.data, batch_size=None)
            self.values[1,:] = gene.classes[np.argmax(probs, axis=1)]
            self.values[0,:] = gene.classes[np.argmax(gene.targets, axis=1)]
            self.values[2,:] = [np.average(gene.classes, weights=probs[i]) for i in range(probs.shape[0])]
        return 0

    def plot_scatter(self, MAP=True, file=None):
        """
        Plot scatter plot (on testing set)
        """
        if MAP == True:
            plt.scatter(self.values[0,:], self.values[1,:], marker='o')
        else:
            plt.scatter(self.values[0,:], self.values[2,:], marker='o')
        #plt.title('Relationship between true and predicted values')
        plt.xlabel('True')
        plt.ylabel('Predicted')
        if file==None:
            plt.show()
        else:
            plt.savefig(file)
        return 0

    def plot_cm(self, classes, file=None):
        """
        Plot confusion matrix (on testing set)
        """
        cm = confusion_matrix(self.values[0,:], self.values[1,:])
        accuracy = np.trace(cm) / float(np.sum(cm))
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

        fig = plt.figure()
        plt.imshow(cm, interpolation='nearest', cmap=cmap)
        plt.title(title)
        plt.colorbar()
        title = 'Confusion matrix'
        cmap = plt.cm.Blues

        tick_marks = np.arange(len(classes))
        plt.xticks(tick_marks, classes, fontsize=8)
        plt.yticks(tick_marks, classes, fontsize=8)

        thresh = cm.max() / 1.5
        for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
            plt.text(j, i, "{:0.4f}".format(cm[i, j]), horizontalalignment="center", color="white" if cm[i, j] > thresh else "black")

        plt.tight_layout()
        plt.ylabel('True label')
        plt.xlabel('Predicted label\naccuracy={:0.4f}'.format(accuracy))
        plt.show()

        if (file==None):
            plt.show()
        else:
            plt.savefig(file)
        return 0

    def save(self, file):
        """
        Save to file
        """
        with open(file,'wb') as fp:
            pickle.dump(self, fp)

        return 0



